import React, { useState, useEffect, useRef } from 'react';
import { Layout, Row, Col, Typography, theme, Tabs, Dropdown, Space, message as antdMessage, Drawer, Button, Spin, Result } from 'antd';
import { UserOutlined, LogoutOutlined, KeyOutlined, DownOutlined, PartitionOutlined, BarChartOutlined } from '@ant-design/icons';
import axios from 'axios';
import ChatInterface from './components/ChatInterface';
import StateVisualizer from './components/StateVisualizer';
import PersonalityEditor from './components/PersonalityEditor';
import WorkflowVisualizer from './components/WorkflowVisualizer';
import EmotionTrendChart from './components/EmotionTrendChart';
import EngagementChart from './components/EngagementChart';
import LogViewer from './components/LogViewer';
import CommunicationAnalysisCard from './components/CommunicationAnalysisCard';
import PersonalityTrendChart from './components/PersonalityTrendChart';
import UserLLMConfig from './components/UserLLMConfig';
import Auth from './components/Auth';
import LocalUnlock from './components/LocalUnlock';
import ChangePasswordModal from './components/ChangePasswordModal';
import AnalysisDashboard from './components/AnalysisDashboard';
import WhitelistManager from './components/WhitelistManager';
import { API_BASE_URL } from './config';

const { Header, Content } = Layout;
const { Title } = Typography;

const parseJwtPayload = (token: string): any | null => {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const json = decodeURIComponent(
      Array.from(atob(padded))
        .map(c => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join('')
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
};

const isJwtExpired = (token: string, skewSeconds = 30) => {
  const payload = parseJwtPayload(token);
  const exp = payload?.exp;
  if (typeof exp !== 'number') return true;
  const nowSeconds = Math.floor(Date.now() / 1000);
  return exp <= (nowSeconds + skewSeconds);
};

// Initialize axios header from localStorage immediately
const storedToken = localStorage.getItem('token');
if (storedToken && !isJwtExpired(storedToken)) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
} else if (storedToken) {
    localStorage.removeItem('token');
}

const EMPTY_VISUAL_STATE = {
  emotions: [],
  personality: 'Unknown',
  weights: {
    Eros: 0,
    Ludus: 0,
    Storge: 0,
    Pragma: 0,
    Mania: 0,
    Agape: 0
  },
  engagementHistory: [] as any[],
  emotionHistory: [] as any[],
  personalityHistory: [] as any[]
};

const App: React.FC = () => {
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const [token, setToken] = useState<string | null>(() => {
    const t = localStorage.getItem('token');
    if (!t) return null;
    if (isJwtExpired(t)) {
      localStorage.removeItem('token');
      return null;
    }
    return t;
  });
  const [username, setUsername] = useState<string | null>(localStorage.getItem('username'));
  const [isSuperUser, setIsSuperUser] = useState<boolean>(localStorage.getItem('isSuperUser') === 'true');
  const [isChangePasswordModalVisible, setIsChangePasswordModalVisible] = useState(false);
  const [activeTab, setActiveTab] = useState('1');
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [authChecked, setAuthChecked] = useState<boolean>(() => token === null);
  // 桌面版(嵌入模式):由本地会话获取成功判定。用于隐藏 server 部署才有意义的功能页。
  const [isDesktopMode, setIsDesktopMode] = useState<boolean>(
    () => localStorage.getItem('desktopMode') === 'true'
  );
  // 本地会话请求去重:StrictMode 双挂载 / 竞态重试都可能并发触发,
  // 若不去重会重复建会话并反复触发后台角色卡生成(日志刷屏)。
  const localSessionInFlight = useRef<Promise<any> | null>(null);

  // 后端就绪状态机。
  //
  // 踩过的坑:原实现只试一次 local_session,失败就 setIsDesktopMode(false) 落到登录界面 ——
  // 而登录/注册在嵌入模式下被刻意禁用(返回 404),于是用户进了一条死路。
  // 触发条件很平常:后端要加载 torch/transformers,实测需 30~45 秒才就绪,
  // 用户打开得比它快就必然命中。
  //
  // 根因是没人负责"后端还没起来"这个状态,把**瞬时不可用**误判成了**部署形态**。
  // 现在严格区分:
  //   404          → 确实是 server 部署 → 显示登录界面
  //   连接失败/5xx → 后端仍在启动     → 显示启动中并持续重试
  const [bootState, setBootState] = useState<'starting' | 'ready' | 'locked' | 'server-mode' | 'error'>(
    () => (localStorage.getItem('desktopMode') === 'true' ? 'ready' : 'starting')
  );
  const bootDeadlineRef = useRef<number>(0);

  useEffect(() => {
    if (token) {
        axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
        localStorage.setItem('token', token);
    } else {
        delete axios.defaults.headers.common['Authorization'];
        localStorage.removeItem('token');
    }
  }, [token]);

  useEffect(() => {
      if (username) {
          localStorage.setItem('username', username);
      } else {
          localStorage.removeItem('username');
      }
  }, [username]);

  useEffect(() => {
      localStorage.setItem('isSuperUser', String(isSuperUser));
  }, [isSuperUser]);

  const handleLogin = (newToken: string, newUsername: string, newIsSuperUser: boolean) => {
      // Set header and localStorage immediately to avoid race condition with child components mounting
      axios.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
      localStorage.setItem('token', newToken);
      setToken(newToken);
      setUsername(newUsername);
      setIsSuperUser(newIsSuperUser);
  };

  const handleLogout = () => {
      setToken(null);
      setUsername(null);
      setIsSuperUser(false);
      localStorage.removeItem('isSuperUser');
      setVisualState(EMPTY_VISUAL_STATE);
      setLogs([]);
      setAiName("Whisper");
      setTraceData(null);
      setLatestUserMessageId(null);
  };

  useEffect(() => {
    let cancelled = false;

    const validate = async () => {
      if (!token) {
        // 桌面版:数据全在本机,不应要求用户注册/登录。尝试取本地会话,
        // 成功即"打开就能用";该端点仅在嵌入模式可用,server 部署返回 404,
        // 此时回落到原有登录界面。
        try {
          if (!localSessionInFlight.current) {
            localSessionInFlight.current = axios
              .post(`${API_BASE_URL}/api/auth/local_session`)
              .finally(() => { localSessionInFlight.current = null; });
          }
          const res = await localSessionInFlight.current;
          if (!cancelled && res.data?.access_token) {
            // 同步设置默认头:setToken 触发的 useEffect 是异步的,
            // 期间发出的请求会因缺少 Authorization 而 401 —— 这正是死循环的起点。
            axios.defaults.headers.common['Authorization'] = `Bearer ${res.data.access_token}`;
            setToken(res.data.access_token);
            setUsername('local');
            setIsSuperUser(Boolean(res.data.is_superuser));
            setIsDesktopMode(true);
            localStorage.setItem('desktopMode', 'true');
            setBootState('ready');
            setAuthChecked(true);
            return;
          }
        } catch (e: any) {
          if (cancelled) return;
          const status = e?.response?.status;
          if (status === 404) {
            // 后端明确答复"此端点不可用" → 确实是 server 部署,登录界面是对的出口
            setIsDesktopMode(false);
            localStorage.removeItem('desktopMode');
            setBootState('server-mode');
            setAuthChecked(true);
            return;
          }
          if (status === 401) {
            // 已设本地隐私锁,需要密码。这是**可重试**的状态,不是部署形态 ——
            // 保持桌面模式,显示解锁界面即可(见 services/local_lock.py)。
            setIsDesktopMode(true);
            setBootState('locked');
            setAuthChecked(true);
            return;
          }
          // 连接失败 / 5xx:后端仍在启动。绝不能据此判定部署形态 —— 那会把用户
          // 推进被禁用的登录界面。保持"启动中"并重试。
          if (!bootDeadlineRef.current) {
            bootDeadlineRef.current = Date.now() + 180_000; // 冷启动最长等 3 分钟
          }
          if (Date.now() < bootDeadlineRef.current) {
            setBootState('starting');
            setTimeout(() => { if (!cancelled) validate(); }, 2000);
            return;
          }
          setBootState('error');
          setAuthChecked(true);
          return;
        }
        if (!cancelled) setAuthChecked(true);
        return;
      }

      if (!cancelled) setAuthChecked(false);
      try {
        await axios.get(`${API_BASE_URL}/api/chat/history?mode=count&limit=1&_t=${Date.now()}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!cancelled) setAuthChecked(true);
      } catch {
        if (cancelled) return;
        handleLogout();
        setAuthChecked(true);
      }
    };

    validate();
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Add axios interceptor to handle 401 Unauthorized globally
  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      response => response,
      async error => {
        const status = error.response?.status;
        // axios 的请求配置类型上没有自定义字段,这里挂一个重试标记
        const original: any = error.config;
        if (status !== 401 && status !== 403) return Promise.reject(error);

        if (!localStorage.getItem('desktopMode')) {
          setToken(null);
          setUsername(null);
          return Promise.reject(error);
        }

        // 桌面版:不能清 token(清了会触发重新挂载 → local_session → 在途旧头
        // 继续 401 → 再清 … 的死循环),但也不能什么都不做 —— 令牌真的过期时
        // 前端会一直拿着死令牌重试,表现为满屏 401。
        // 正确做法:就地换一个新的本地会话令牌并重放本次请求,全程不动 token 状态。
        // _retried 保证每个请求最多换一次令牌,换完仍 401 就如实抛出。
        if (original?._retried || original?.url?.includes('/api/auth/local_session')) {
          return Promise.reject(error);
        }
        original._retried = true;
        try {
          if (!localSessionInFlight.current) {
            localSessionInFlight.current = axios
              .post(`${API_BASE_URL}/api/auth/local_session`)
              .finally(() => { localSessionInFlight.current = null; });
          }
          const res = await localSessionInFlight.current;
          const fresh = res.data?.access_token;
          if (!fresh) return Promise.reject(error);
          axios.defaults.headers.common['Authorization'] = `Bearer ${fresh}`;
          localStorage.setItem('token', fresh);
          original.headers = { ...(original.headers || {}), Authorization: `Bearer ${fresh}` };
          return axios(original);
        } catch {
          return Promise.reject(error);
        }
      }
    );
    return () => {
      axios.interceptors.response.eject(interceptor);
    };
  }, []);

  const [visualState, setVisualState] = useState(EMPTY_VISUAL_STATE);

  const [logs, setLogs] = useState<any[]>([]);
  const [aiName, setAiName] = useState<string>("Whisper");
  const [traceData, setTraceData] = useState<any>(null); // New Trace State
  const [latestUserMessageId, setLatestUserMessageId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadCommonSettings = async () => {
      if (!token) {
        if (!cancelled) {
          setAiName("Whisper");
        }
        return;
      }

      try {
        const res = await axios.get(`${API_BASE_URL}/api/config/common`);
        if (!cancelled && res.data?.name) {
          setAiName(res.data.name);
        }
      } catch (error) {
        if (!cancelled) {
          console.error('Failed to load common settings', error);
        }
      }
    };

    loadCommonSettings();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleStateUpdate = React.useCallback((data: any) => {
    setVisualState(prev => {
        // Append new score to history if present
        const newEngagementHistory = data.engagement_score !== undefined 
            ? [...(prev.engagementHistory || []), { 
                index: (prev.engagementHistory?.length || 0) + 1, 
                score: data.engagement_score,
                user_input: data.user_input,
                agent_response: data.response
              }]
            : prev.engagementHistory;

        // Append new emotion scores to history
        const newEmotionHistory = data.all_emotions 
            ? [...(prev.emotionHistory || []), { 
                index: (prev.emotionHistory?.length || 0) + 1, 
                ...data.all_emotions
              }]
            : prev.emotionHistory;
        
        // Append new personality weights to history
        const newPersonalityHistory = data.weights
             ? [...(prev.personalityHistory || []), {
                 index: (prev.personalityHistory?.length || 0) + 1,
                 ...data.weights
             }]
             : prev.personalityHistory;

        return {
            ...prev,
            ...data,
            engagementHistory: newEngagementHistory,
            emotionHistory: newEmotionHistory,
            personalityHistory: newPersonalityHistory
        };
    });

    if (data.logs && Array.isArray(data.logs)) {
      setLogs(prev => [...prev, ...data.logs]);
    }
    
    // Update Trace Data if available
    if (data.workflow_trace) {
        setTraceData(data.workflow_trace);
    }
    
    if (data.user_message_id) {
        setLatestUserMessageId(data.user_message_id);
    }
  }, []);

  const handleHistoryLoad = React.useCallback((historyData: any[]) => {
      const engagementHistory: any[] = [];
      const emotionHistory: any[] = [];
      const personalityHistory: any[] = [];
      const allLogs: any[] = [];
      
      let lastState: any = {};
      let index = 1;

      historyData.forEach(data => {
          let hasUpdate = false;
          
          if (data.engagement_score !== undefined) {
              engagementHistory.push({ 
                  index, 
                  score: data.engagement_score,
                  user_input: data.user_input,
                  agent_response: data.agent_response
              });
              hasUpdate = true;
          }
          if (data.all_emotions) {
              emotionHistory.push({ index, ...data.all_emotions });
              hasUpdate = true;
          }
          if (data.weights) {
              personalityHistory.push({ index, ...data.weights });
              hasUpdate = true;
          }
          if (data.logs) {
              allLogs.push(...data.logs);
          }
          
          // Extract logs from workflow_trace
          if (data.workflow_trace) {
              if (data.workflow_trace.analyze_communication_style?.output?.ui_card_data) {
                  allLogs.push(data.workflow_trace.analyze_communication_style.output.ui_card_data);
              }
              lastState.workflow_trace = data.workflow_trace;
          }
          
          // Capture latest state
          if (data.emotions) {
              // Convert [label, score] tuples to {label, score} objects if needed
              if (Array.isArray(data.emotions) && Array.isArray(data.emotions[0])) {
                  lastState.emotions = data.emotions.map((item: any) => ({
                      label: item[0],
                      score: item[1]
                  }));
              } else {
                  lastState.emotions = data.emotions;
              }
          }
          if (data.personality) lastState.personality = data.personality;
          if (data.weights) lastState.weights = data.weights;

          if (hasUpdate) index++;
      });

      setVisualState({
          ...EMPTY_VISUAL_STATE,
          ...lastState,
          engagementHistory,
          emotionHistory,
          personalityHistory
      });
      setLogs(allLogs);
      setTraceData(lastState.workflow_trace ?? null);
      setLatestUserMessageId(null);
  }, []);

  const handleSessionEnd = (duration: number, count: number) => {
      console.log(`Session ended: ${duration}s, ${count} msgs`);
  };
  
  const handleNameUpdate = (name: string) => {
      setAiName(name);
  };

  const items = [
    {
      key: '1',
      label: '对话界面',
      children: (
        <div style={{ height: '100%', position: 'relative', overflow: 'hidden' }}>
             <div style={{ height: '100%', overflow: 'hidden' }}>
                <ChatInterface 
                    token={token}
                    onUnauthorized={handleLogout}
                    onStateUpdate={handleStateUpdate} 
                    onHistoryLoad={handleHistoryLoad}
                    onSessionEnd={handleSessionEnd} 
                    aiName={aiName} 
                    onConfigRequired={() => {
                        antdMessage.warning("请先配置大模型参数");
                        setActiveTab('user-config');
                    }}
                />
             </div>
             
             <Drawer
                title="分析面板"
                placement="right"
                width={800}
                onClose={() => setDrawerVisible(false)}
                open={drawerVisible}
                styles={{ body: { padding: 0, background: '#f5f5f5' } }}
             >
                <div style={{ padding: '24px' }}>
                    <AnalysisDashboard 
                        visualState={visualState}
                        logs={logs}
                        latestUserMessageId={latestUserMessageId}
                        isSuperUser={isSuperUser}
                    />
                </div>
             </Drawer>
        </div>
      ),
    },
    ...(isSuperUser ? [
      {
        key: 'user-config',
        label: '系统设置',
        children: <div style={{ height: '100%', overflow: 'auto', paddingRight: '10px' }}><UserLLMConfig /></div>,
      },
      // 白名单管理是 server 部署概念(控制谁能注册)。桌面版是单机应用,
      // 本机用户即拥有者,该页无意义且后端已关闭对应接口,故隐藏。
      ...(isDesktopMode ? [] : [{
        key: 'whitelist-manager',
        label: '白名单管理',
        children: <div style={{ height: '100%', overflow: 'auto', paddingRight: '10px' }}><WhitelistManager /></div>,
      }])
    ] : []),
    {
      key: '2',
      label: '人格编辑器',
      children: <div style={{ height: '100%', overflow: 'auto', paddingRight: '10px' }}><PersonalityEditor onNameUpdate={handleNameUpdate} /></div>,
    },
    ...(isSuperUser ? [
        {
          key: '3',
          label: '运行日志',
          children: <div style={{ height: '100%', overflow: 'auto' }}><LogViewer logs={logs} /></div>,
        },
        {
          key: '4',
          label: (
            <span>
              <PartitionOutlined />
              工作流编排
            </span>
          ),
          children: (
            <div style={{ height: '100%', overflow: 'hidden' }}>
              {activeTab === '4' ? <WorkflowVisualizer traceData={traceData} /> : null}
            </div>
          ),
        }
    ] : [])
  ];

  // 后端冷启动要 30~45 秒(加载 torch/transformers)。此时必须显示"启动中",
  // 而不是回落到登录界面 —— 嵌入模式下登录/注册是禁用的(404),那是条死路。
  if (!token && bootState === 'starting') {
    return <Spin size="large" tip="正在启动本地服务(首次启动约需 30 秒)…" fullscreen />;
  }

  // 已设本地隐私锁:显示解锁界面。这是可重试状态,不是死路 ——
  // 输错密码只是再试一次,不会把用户推到被禁用的注册/登录页。
  if (!token && bootState === 'locked') {
    return <LocalUnlock onUnlocked={(t, superUser) => {
      axios.defaults.headers.common['Authorization'] = `Bearer ${t}`;
      localStorage.setItem('token', t);
      localStorage.setItem('desktopMode', 'true');
      setToken(t);
      setUsername('local');
      setIsSuperUser(superUser);
      setIsDesktopMode(true);
      setBootState('ready');
      setAuthChecked(true);
    }} />;
  }

  if (!token && bootState === 'error') {
    return (
      <Result
        status="warning"
        title="本地服务未能启动"
        subTitle="后端进程可能异常退出。请退出应用后重新打开;若反复出现,请查看运行日志。"
        extra={<Button type="primary" onClick={() => window.location.reload()}>重试</Button>}
      />
    );
  }

  if (!token) {
    return <Auth onLogin={handleLogin} />;
  }

  if (!authChecked) {
    return <Spin size="large" tip="正在验证登录状态..." fullscreen />;
  }

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <style>
        {`
          .full-height-tabs {
            height: 100%;
            display: flex;
            flex-direction: column;
          }
          .full-height-tabs .ant-tabs-content-holder {
            flex: 1;
            overflow: auto;
            min-height: 0; /* Critical for flexbox scrolling */
          }
          .full-height-tabs .ant-tabs-content {
            height: 100%;
          }
          .full-height-tabs .ant-tabs-tabpane {
            height: 100%;
          }
        `}
      </style>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#001529', padding: '0 24px' }}>
        <Title level={3} style={{ color: 'white', margin: 0 }}>{aiName}</Title>
        <Space>
            {activeTab === '1' && (
                <Button 
                    type="text" 
                    icon={<BarChartOutlined />} 
                    style={{ color: 'white' }}
                    onClick={() => setDrawerVisible(true)}
                >
                    分析面板
                </Button>
            )}
            <Dropdown menu={{
                items: [
                    {
                        key: 'change-password',
                        label: '修改密码',
                        icon: <KeyOutlined />,
                        onClick: () => setIsChangePasswordModalVisible(true)
                    },
                    {
                        key: 'logout',
                        label: '退出登录',
                        icon: <LogoutOutlined />,
                        onClick: handleLogout
                    }
                ]
            }}>
                <span style={{ color: 'white', cursor: 'pointer' }}>
                    <UserOutlined /> {username} <DownOutlined />
                </span>
            </Dropdown>
        </Space>
        <ChangePasswordModal 
            visible={isChangePasswordModalVisible} 
            onCancel={() => setIsChangePasswordModalVisible(false)}
            onSuccess={() => setIsChangePasswordModalVisible(false)}
        />
      </Header>
      <Content style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px', overflow: 'hidden' }}>
        <Row gutter={24} style={{ flex: 1, minHeight: 0 }}>
          <Col span={24} style={{ height: '100%' }}>
            <div style={{ 
              background: colorBgContainer, 
              padding: 24, 
              borderRadius: borderRadiusLG,
              height: '100%',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column'
            }}>
              <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} className="full-height-tabs" />
            </div>
          </Col>
        </Row>
      </Content>
    </Layout>
  );
};


export default App;
