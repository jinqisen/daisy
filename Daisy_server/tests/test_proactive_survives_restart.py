"""
主动关心的长期状态必须跨重启有效。

嵌入模式下 Redis 是**进程内 fakeredis,重启即空**。而主动关心把三件事都放在了
那里:作息统计、每日配额、上次开口时间。三件事的共同点是**它们都描述过去**,
本就不该随进程消失。实际后果:

  - 作息统计:样本数要 ≥10 才被认为可信,而每次重启归零 ——
    「按作息挑时间」实际上从未生效过,永远走冷启动的保守值;
  - 每日配额:**重启即可绕过每日上限**;
  - 冷却时间:重启后记录消失,刚开机就可能立刻打扰。

而这个功能的失败方式是**不对称的** —— 不够热情只是遗憾,打扰是不可逆的
(用户觉得烦就卸载,不会回来)。所以恰恰是这三件事最不能失效。

现在三者都从 chat_history 推导:那是真持久的,而且本来就是同一个事实
(`is_proactive` 字段是上一轮为评估效果加的,这里正好复用,不需要新表)。
Redis 退化为带 TTL 的缓存,丢了自动重算。

顺带修掉两个在这条路径上的真缺陷,见 TestUserIdIsForeignKey / TestTimestampConvention。
"""

import asyncio
import datetime
import inspect
import os
import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.models import ChatHistoryDB, UserDB
from app.models.base import Base

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def db_factory(monkeypatch):
    """
    一个真实(内存)库,并让被测代码的 SessionLocal 指向它。

    必须用 StaticPool + check_same_thread=False:被测代码把查询丢到
    run_in_executor(**另一个线程**)里执行,而 :memory: 库是**每个连接一个**。
    用默认连接池的话,executor 线程会拿到一个全新的空库,
    测试会以 "no such table" 失败 —— 那是夹具的问题,不是实现的问题。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    import app.core.database as database
    import app.services.proactive.service as svc
    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(svc, "SessionLocal", Session)

    with Session() as s:
        s.add(UserDB(username="alice", hashed_password="x"))
        s.commit()
    return Session


def _uid(Session) -> int:
    with Session() as s:
        return s.query(UserDB).filter(UserDB.username == "alice").first().id


def _add_proactive(Session, uid, when: datetime.datetime):
    with Session() as s:
        s.add(ChatHistoryDB(session_id="t", user_id=uid, role="ai",
                            content="在忙吗", timestamp=when, is_proactive=True))
        s.commit()


class TestDailyQuotaSurvivesRestart:
    """
    核心回归:配额是"今天已经打扰过几次"的事实,不能随进程消失。
    """

    def test_counts_todays_proactive_messages(self, db_factory):
        from app.services.proactive.service import ProactiveService

        uid = _uid(db_factory)
        now = datetime.datetime.utcnow()
        for _ in range(2):
            _add_proactive(db_factory, uid, now)

        n = asyncio.run(ProactiveService._get_daily_count(uid))
        assert n == 2, f"今日配额应为 2,实际 {n}"

    def test_yesterdays_messages_do_not_count(self, db_factory):
        """配额是**每日**的,昨天的不该占用今天的额度。"""
        from app.services.proactive.service import ProactiveService

        uid = _uid(db_factory)
        _add_proactive(db_factory, uid,
                       datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=2))

        assert asyncio.run(ProactiveService._get_daily_count(uid)) == 0

    def test_normal_replies_do_not_count(self, db_factory):
        """普通回复不是打扰,不能占配额,否则正常聊天会把额度吃光。"""
        from app.services.proactive.service import ProactiveService

        uid = _uid(db_factory)
        with db_factory() as s:
            s.add(ChatHistoryDB(session_id="t", user_id=uid, role="ai",
                                content="嗯嗯", timestamp=datetime.datetime.utcnow()))
            s.commit()

        assert asyncio.run(ProactiveService._get_daily_count(uid)) == 0

    def test_unknown_user_is_treated_as_over_quota(self, db_factory):
        """
        身份不明时必须**倾向于不发**。返回 0 会被上游当作"今天还没发过"而放行 ——
        在这个功能上,错误的方向比错误本身更要紧。
        """
        from app.services.proactive.service import ProactiveService

        from app.core.config import settings
        n = asyncio.run(ProactiveService._get_daily_count(None))
        assert n >= settings.PROACTIVE_MAX_DAILY, \
            "解析不到用户时没有拦住 —— 会向身份不明的对象发消息"


class TestCooldownSurvivesRestart:

    def test_reads_last_proactive_from_db(self, db_factory):
        from app.services.proactive.service import ProactiveService

        uid = _uid(db_factory)
        when = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        _add_proactive(db_factory, uid, when)

        ts = asyncio.run(ProactiveService._get_last_proactive_time(uid))
        assert ts is not None, "冷却记录丢失 —— 重启后会立刻再次打扰"
        # 允许几秒误差,但绝不允许差出一个时区(见 TestTimestampConvention)
        expected = when.replace(tzinfo=datetime.timezone.utc).timestamp()
        assert abs(ts - expected) < 5, \
            f"时间戳解释错误,差 {(ts - expected) / 3600:.1f} 小时"

    def test_none_when_never_sent(self, db_factory):
        from app.services.proactive.service import ProactiveService

        assert asyncio.run(
            ProactiveService._get_last_proactive_time(_uid(db_factory))
        ) is None

    def test_db_failure_blocks_instead_of_allowing(self, db_factory, monkeypatch):
        """
        读不到就返回"刚刚发过",让冷却拦住这一轮。
        返回 None 会被上游当成"从没发过"而直接放行 —— 方向反了。
        """
        import app.services.proactive.service as svc

        def _boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(svc, "SessionLocal", _boom)

        ts = asyncio.run(svc.ProactiveService._get_last_proactive_time(_uid(db_factory)))
        assert ts is not None, "数据库故障时放行了 —— 应当倾向于不打扰"
        assert abs(ts - datetime.datetime.now().timestamp()) < 5


class TestActivityStatsComeFromHistory:
    """
    作息统计原先是 Redis 里一个**无 TTL** 的 hincrby 计数器,重启即空,
    而可信阈值是 10 条 —— 两者合起来让这个统计永远攒不够样本。
    """

    def test_histogram_derived_from_chat_history(self, db_factory, monkeypatch):
        from app.services.proactive.state import StateService

        uid = _uid(db_factory)
        # 造 12 条本地时间 14 点的用户消息
        local_14 = datetime.datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
        as_utc = local_14 - datetime.datetime.now().astimezone().utcoffset()
        with db_factory() as s:
            for _ in range(12):
                s.add(ChatHistoryDB(session_id="t", user_id=uid, role="user",
                                    content="hi", timestamp=as_utc))
            s.commit()

        import app.core.database as database
        monkeypatch.setattr(database, "SessionLocal", db_factory)

        p = asyncio.run(StateService.get_activity_probability("alice", 14))
        assert p > 0.9, f"14 点的活跃概率应接近 1,实际 {p}"
        assert asyncio.run(StateService.get_activity_probability("alice", 3)) < 0.1

    def test_no_standalone_counter_left(self):
        """
        残留的独立计数器会重新引入"计数器与事实不一致"的可能。
        """
        from app.services.proactive import state

        src = inspect.getsource(state)
        # 只看真实调用 —— 注释和文档字符串里会提到 hincrby(那正是在解释这个缺陷)
        assert not re.search(r"redis_client(?:\.redis)?\.hincrby\(", src), \
            "作息统计仍在用独立计数器 —— 重启即空,统计永远攒不够样本"

    def test_sample_is_bounded(self):
        """无上界的话,历史越长这条查询越慢,而它在每次判定时都会走到。"""
        from app.services.proactive.state import StateService

        assert StateService.ACTIVITY_SAMPLE_LIMIT > 0
        src = inspect.getsource(StateService._activity_histogram)
        assert "limit(" in src.lower(), "作息统计查询没有上界"


class TestUserIdIsForeignKey:
    """
    `chat_history.user_id` 是指向 users.id 的**整数外键**,而主动关心这条链路上
    的 user_id 自始至终是**用户名字符串**。两者曾被直接混用:用户名被写进整数列,
    SQLite 弱类型照单全收 —— 那条消息不属于任何用户,既不会出现在对话历史里,
    也无法用于统计,连带 is_proactive 标记一起失效。
    """

    def test_send_message_takes_db_id(self):
        from app.services.proactive.service import ProactiveService

        sig = inspect.signature(ProactiveService._send_message)
        assert "db_user_id" in sig.parameters, \
            "_send_message 没有区分用户名与数据库 ID —— 会把用户名写进整数外键列"

    def test_stored_row_is_linked_to_user(self, db_factory):
        """行为验证:写完之后这条消息必须真的能通过外键查回来。"""
        import app.services.proactive.service as svc

        uid = _uid(db_factory)
        with db_factory() as s:
            asyncio.run(svc.ProactiveService._send_message(
                "alice", uid, "在忙吗", s, is_online=False
            ))

        with db_factory() as s:
            rows = (s.query(ChatHistoryDB)
                     .filter(ChatHistoryDB.user_id == uid,
                             ChatHistoryDB.is_proactive.is_(True))
                     .all())
        assert len(rows) == 1, "主动消息没有正确挂到用户上 —— 历史里看不到,也统计不到"


class TestTimestampConvention:
    """
    表里其余行是 naive UTC(utc_now_naive),主动消息却写 datetime.now()(本地)。
    在 UTC+8 下它比同表其他行超前 8 小时,会把排序、"今天几条"、冷却一起算错。
    """

    def test_send_message_writes_utc(self, db_factory):
        import app.services.proactive.service as svc

        uid = _uid(db_factory)
        before = datetime.datetime.utcnow()
        with db_factory() as s:
            asyncio.run(svc.ProactiveService._send_message(
                "alice", uid, "在忙吗", s, is_online=False
            ))
        after = datetime.datetime.utcnow()

        with db_factory() as s:
            ts = s.query(ChatHistoryDB.timestamp).first()[0]
        assert before - datetime.timedelta(seconds=5) <= ts <= after + datetime.timedelta(seconds=5), \
            f"写入的时间不是 UTC(与同表其他行差一个时区): {ts}"

    def test_epoch_helper_treats_naive_as_utc(self):
        from app.core.time_utils import naive_utc_to_epoch

        naive = datetime.datetime(2026, 1, 1, 12, 0, 0)
        expected = naive.replace(tzinfo=datetime.timezone.utc).timestamp()
        assert naive_utc_to_epoch(naive) == expected

    def test_no_raw_timestamp_calls_on_db_rows(self):
        """
        直接 `.timestamp()` 是这个 bug 的形态。库里取出的时间一律走
        naive_utc_to_epoch,否则会被按本地时区解释。
        """
        for mod_path in ("app/services/proactive/state.py",
                         "app/services/proactive/service.py"):
            src = open(os.path.join(SERVER, mod_path), encoding="utf-8").read()
            code = "\n".join(l for l in src.splitlines()
                             if not l.strip().startswith("#"))
            assert not re.search(r"row\[0\]\.timestamp\(\)", code), \
                f"{mod_path} 仍在直接把库里的 naive UTC 当本地时间解释"


class TestRedisIsCacheOnly:
    """
    收敛后的规则:**SQLite 是唯一真源,Redis 只是缓存** ——
    任何写入 Redis 的 key 都必须带 TTL,丢了能重算。

    这条护栏针对的是这轮所有缺陷的共同根因:把长期事实塞进了会消失的地方。
    """

    # 允许无 TTL 的写入(都是会话期状态,生命周期本就 ≤ 单次运行)。
    # 这是棘轮基线:只允许减少。
    ALLOWED_NO_TTL = {
        "app/core/cache.py",           # 客户端自身的实现
        "app/services/system/init_data.py",  # 启动种子,随进程重建
        "app/services/memory/topic_agent.py",  # 已带 ttl,见下方正则说明
    }

    def test_proactive_writes_no_untracked_state(self):
        """
        主动关心不得再往 Redis 写任何长期状态 —— 这正是本轮三个缺陷的来源。
        """
        for mod_path in ("app/services/proactive/state.py",
                         "app/services/proactive/service.py"):
            src = open(os.path.join(SERVER, mod_path), encoding="utf-8").read()
            code = "\n".join(l for l in src.splitlines()
                             if not l.strip().startswith("#"))
            for m in re.finditer(r"redis_client(?:\.redis)?\.(set|hset|hincrby|incr)\(",
                                 code):
                call = code[m.start(): m.start() + 260]
                assert "ttl=" in call or "ex=" in call, \
                    (f"{mod_path} 中 {m.group(1)}() 写入 Redis 却没有 TTL ——"
                     f" 长期事实请落 SQLite,Redis 只做缓存:\n{call[:160]}")


class TestSameBugElsewhere:
    """
    "把库里的 naive UTC 当本地时间"这个缺陷不止一处。
    workflow/nodes/emotion.py 里同样的写法后果更隐蔽:它算的是用户的响应时长,
    在 UTC+8 下恒定多出 8 小时 —— M_rtl(响应时间)这一项因此永远饱和,
    在参与度评分里退化成常量,喂给 Reflexion / RL 的信号是坏的,
    而表面上一切正常,没有任何报错。
    """

    def test_emotion_node_uses_utc_helper(self):
        src = open(os.path.join(SERVER, "app", "workflow", "nodes", "emotion.py"),
                   encoding="utf-8").read()
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        assert not re.search(r"\.timestamp\.timestamp\(\)", code), \
            "仍在把库里的 naive UTC 当本地时间 —— 响应时长会恒定多出一个时区"
        assert "naive_utc_to_epoch" in code

    def test_response_time_is_plausible(self):
        """
        行为验证:刚回复过的消息,算出来的响应时长应当是秒级,而不是几小时。
        """
        import time as _t

        from app.core.time_utils import naive_utc_to_epoch, utc_now_naive

        ai_ts = naive_utc_to_epoch(utc_now_naive())
        response_time = max(0.1, _t.time() - ai_ts)
        assert response_time < 60, \
            f"响应时长算成了 {response_time / 3600:.1f} 小时 —— 时区解释错了"
