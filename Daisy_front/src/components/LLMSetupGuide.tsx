import React, { useEffect, useState } from 'react';
import { Card, Radio, Input, Button, Alert, Typography, Space, message, Spin } from 'antd';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Text, Title, Paragraph, Link } = Typography;

interface ProviderInfo {
    provider: string;
    name: string;
    description?: string;
    model?: string;
}

interface Props {
    /** 配置成功后回调(用于让父组件重新检查角色卡/解除门禁) */
    onConfigured?: () => void;
}

/**
 * 首次运行的模型配置引导。
 *
 * 桌面版为 keyless 分发(安装包不含任何 API Key),用户必须先填入自己的密钥才能对话。
 * 此组件面向"尚未配置模型"的场景:任何已登录用户都可使用(不要求管理员权限),
 * 因为桌面版用户自己就是管理员;写入的是系统级密钥(/api/config/llm_keys),
 * 会热重载所有 provider,使工作流内全部 agent 立即生效。
 */
const PROVIDER_KEY_HINTS: Record<string, { envName: string; applyUrl: string; label: string }> = {
    huaweicloud: {
        envName: 'MAAS_API_KEY',
        applyUrl: 'https://console.huaweicloud.com/modelarts/',
        label: '华为云 ModelArts API Key',
    },
    siliconflow: {
        envName: 'SILICONFLOW_API_KEY',
        applyUrl: 'https://cloud.siliconflow.cn/account/ak',
        label: '硅基流动 API Key',
    },
    openai: {
        envName: 'OPENAI_API_KEY',
        applyUrl: 'https://platform.openai.com/api-keys',
        label: 'OpenAI API Key',
    },
};

const LLMSetupGuide: React.FC<Props> = ({ onConfigured }) => {
    const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
    const [selected, setSelected] = useState<string>('huaweicloud');
    const [apiKey, setApiKey] = useState('');
    const [searchKey, setSearchKey] = useState('');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    // 区分"从未配置"与"配了但密钥已失效"—— 两者提示语不同,后者更需要明确告知原因
    const [hasInvalidKey, setHasInvalidKey] = useState(false);

    useEffect(() => {
        const load = async () => {
            try {
                const res = await axios.get(`${API_BASE_URL}/api/config/providers`);
                setProviders(res.data || {});
                const first = Object.keys(res.data || {})[0];
                if (first) setSelected(first);
            } catch (e) {
                // provider 列表拉取失败不阻塞:仍可手填密钥
            }
            try {
                const st = await axios.get(`${API_BASE_URL}/api/config/llm_status`);
                setHasInvalidKey(Boolean(st.data?.has_invalid_key));
            } catch (e) {
                // 状态查询失败按"未配置"处理
            }
            setLoading(false);
        };
        load();
    }, []);

    const hint = PROVIDER_KEY_HINTS[selected] || PROVIDER_KEY_HINTS.huaweicloud;

    const handleSave = async () => {
        if (!apiKey.trim()) {
            message.warning('请填入 API Key');
            return;
        }
        setSaving(true);
        try {
            const payload: Record<string, string> = { [hint.envName]: apiKey.trim() };
            // 联网搜索需要独立的密钥;长期记忆已改为跟随对话模型,无需额外密钥
            if (searchKey.trim()) {
                payload['HUAWEI_SEARCH_API_KEY'] = searchKey.trim();
            }
            // 后端会先探活再落盘:密钥填错(如把搜索密钥填进聊天槽位)会当场 400,
            // 而不是等到第一次对话失败、表现成"角色卡一直生成中"。
            const saveRes = await axios.post(`${API_BASE_URL}/api/config/llm_keys`, payload);
            const verdicts = saveRes.data?.verification || {};
            const unverified = Object.entries(verdicts)
                .filter(([, v]: any) => v?.status === 'unverified');

            // 同时把所选 provider 记入用户设置,使后续对话使用该服务商
            try {
                const cur = await axios.get(`${API_BASE_URL}/api/config/common`);
                await axios.post(`${API_BASE_URL}/api/config/common`, {
                    ...cur.data,
                    llm_provider: selected,
                });
            } catch (e) {
                // provider 记录失败不致命,密钥已生效
            }

            if (unverified.length > 0) {
                // 网络不通/服务商抖动时后端会放行,但要如实告知没验成功
                message.warning(String((unverified[0][1] as any).reason || '未能校验密钥,已按有效保存'));
            } else {
                message.success('密钥校验通过,正在初始化角色…');
            }
            onConfigured?.();
        } catch (e: any) {
            const detail = e?.response?.data?.detail || '保存失败,请检查密钥是否正确';
            message.error(String(detail));
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <Spin />;

    return (
        <Card style={{ maxWidth: 560, width: '100%' }}>
            <Title level={4} style={{ marginTop: 0 }}>
                {hasInvalidKey ? '需要更新 API Key' : '先配置一个大模型'}
            </Title>
            {hasInvalidKey ? (
                <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 20 }}
                    message="当前 API Key 已失效"
                    description="服务商拒绝了这个密钥(可能已过期或被撤销)。请填入有效的 API Key 后继续。"
                />
            ) : (
                <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 20 }}
                    message="本应用不内置 API Key"
                    description="为保护你的账号安全,安装包不含任何密钥。请填入你自己的 API Key,它只保存在本机。"
                />
            )}

            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <div>
                    <Text strong>选择服务商</Text>
                    <Radio.Group
                        value={selected}
                        onChange={(e) => setSelected(e.target.value)}
                        style={{ display: 'block', marginTop: 8 }}
                    >
                        <Space direction="vertical">
                            {Object.values(providers).length > 0
                                ? Object.values(providers).map((p) => (
                                    <Radio key={p.provider} value={p.provider}>
                                        {p.name || p.provider}
                                        {p.model ? <Text type="secondary"> · {p.model}</Text> : null}
                                    </Radio>
                                ))
                                : Object.keys(PROVIDER_KEY_HINTS).map((k) => (
                                    <Radio key={k} value={k}>{PROVIDER_KEY_HINTS[k].label}</Radio>
                                ))}
                        </Space>
                    </Radio.Group>
                </div>

                <div>
                    <Text strong>{hint.label}</Text>
                    <Input.Password
                        style={{ marginTop: 8 }}
                        placeholder="粘贴你的 API Key"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        onPressEnter={handleSave}
                    />
                    <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 6, marginBottom: 0 }}>
                        没有密钥?<Link href={hint.applyUrl} target="_blank" rel="noreferrer"> 前往申请</Link>
                    </Paragraph>
                </div>

                {/* 长期记忆现在跟随对话模型走,不再单独需要硅基流动密钥;
                    真正还需要额外密钥的是联网搜索,故这里只留它。 */}
                <div>
                    <Text strong>联网搜索 API Key</Text>
                    <Text type="secondary">(可选)</Text>
                    <Input.Password
                        style={{ marginTop: 8 }}
                        placeholder="留空则她无法查天气、新闻等实时信息"
                        value={searchKey}
                        onChange={(e) => setSearchKey(e.target.value)}
                        onPressEnter={handleSave}
                    />
                    <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 6, marginBottom: 0 }}>
                        <Link href="https://console.huaweicloud.com/csb/" target="_blank" rel="noreferrer">前往申请华为云搜索服务</Link>
                    </Paragraph>
                </div>

                <Button type="primary" size="large" block loading={saving} onClick={handleSave}>
                    {saving ? '正在校验密钥…' : '保存并开始'}
                </Button>
            </Space>
        </Card>
    );
};

export default LLMSetupGuide;
