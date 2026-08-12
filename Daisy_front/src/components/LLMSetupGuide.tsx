import React, { useEffect, useState } from 'react';
import { Card, Input, Button, Alert, Typography, Space, message, Spin, Collapse } from 'antd';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Text, Title, Paragraph, Link } = Typography;

interface Props {
    onConfigured?: () => void;
}

const LLMSetupGuide: React.FC<Props> = ({ onConfigured }) => {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [hasInvalidKey, setHasInvalidKey] = useState(false);

    const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1');
    const [apiKey, setApiKey] = useState('');
    const [modelName, setModelName] = useState('gpt-4o');
    const [searchKey, setSearchKey] = useState('');

    useEffect(() => {
        const load = async () => {
            try {
                const st = await axios.get(`${API_BASE_URL}/api/config/llm_status`);
                setHasInvalidKey(Boolean(st.data?.has_invalid_key));
                if (st.data?.base_url) setBaseUrl(st.data.base_url);
                if (st.data?.model_name) setModelName(st.data.model_name);
            } catch (e) {
                // ignore
            }
            setLoading(false);
        };
        load();
    }, []);

    const handleSave = async () => {
        if (!apiKey.trim()) { message.warning('请填入 API Key'); return; }
        if (!baseUrl.trim()) { message.warning('请填入 Base URL'); return; }
        if (!modelName.trim()) { message.warning('请填入模型名称'); return; }
        setSaving(true);
        try {
            const payload: Record<string, string> = {
                OPENAI_API_KEY: apiKey.trim(),
                OPENAI_BASE_URL: baseUrl.trim(),
                LLM_MODEL_NAME: modelName.trim(),
            };
            if (searchKey.trim()) payload['HUAWEI_SEARCH_API_KEY'] = searchKey.trim();

            const saveRes = await axios.post(`${API_BASE_URL}/api/config/llm_keys`, payload);
            const verdicts = saveRes.data?.verification || {};
            const unverified = Object.entries(verdicts)
                .filter(([, v]: any) => v?.status === 'unverified');

            if (unverified.length > 0) {
                message.warning(String((unverified[0][1] as any).reason || '未能校验密钥，已按有效保存'));
            } else {
                message.success('密钥校验通过，正在初始化角色…');
            }
            onConfigured?.();
        } catch (e: any) {
            const detail = e?.response?.data?.detail || '保存失败，请检查密钥和地址是否正确';
            message.error(String(detail));
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <Spin />;

    return (
        <Card style={{ maxWidth: 560, width: '100%' }}>
            <Title level={4} style={{ marginTop: 0 }}>
                {hasInvalidKey ? '需要更新 API Key' : '配置大模型'}
            </Title>
            {hasInvalidKey ? (
                <Alert
                    type="warning" showIcon style={{ marginBottom: 20 }}
                    message="当前 API Key 已失效"
                    description="服务商拒绝了这个密钥（可能已过期或被撤销）。请填入有效的 API Key 后继续。"
                />
            ) : (
                <Alert
                    type="info" showIcon style={{ marginBottom: 20 }}
                    message="兼容所有 OpenAI 接口的服务商"
                    description="支持 OpenAI、DeepSeek、通义千问、硅基流动、智谱等所有提供 OpenAI 兼容 API 的服务。你的 API Key 只保存在本机。"
                />
            )}

            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <div>
                    <Text strong>接口地址（Base URL）</Text>
                    <Input
                        style={{ marginTop: 8 }}
                        placeholder="https://api.openai.com/v1"
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                    />
                    <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                        服务商的 OpenAI 兼容 API 地址，必须以 /v1 结尾
                    </Paragraph>
                </div>

                <div>
                    <Text strong>API Key</Text>
                    <Input.Password
                        style={{ marginTop: 8 }}
                        placeholder="sk-..."
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        onPressEnter={handleSave}
                    />
                    <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                        密钥只保存在本机，不会上传到任何服务器
                    </Paragraph>
                </div>

                <div>
                    <Text strong>模型名称</Text>
                    <Input
                        style={{ marginTop: 8 }}
                        placeholder="gpt-4o / deepseek-chat / qwen-plus ..."
                        value={modelName}
                        onChange={(e) => setModelName(e.target.value)}
                    />
                    <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                        你使用的模型名，如 gpt-4o、deepseek-v3.2、qwen-plus
                    </Paragraph>
                </div>

                <Collapse ghost items={[{
                    key: 'search',
                    label: '联网搜索 API Key（可选）',
                    children: (
                        <div>
                            <Input.Password
                                placeholder="留空则她无法查天气、新闻等实时信息"
                                value={searchKey}
                                onChange={(e) => setSearchKey(e.target.value)}
                                onPressEnter={handleSave}
                            />
                            <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 6, marginBottom: 0 }}>
                                <Link href="https://console.huaweicloud.com/csb/" target="_blank" rel="noreferrer">前往申请华为云搜索服务</Link>
                            </Paragraph>
                        </div>
                    ),
                }]} />

                <Button type="primary" size="large" block loading={saving} onClick={handleSave}>
                    {saving ? '正在校验密钥…' : '保存并开始'}
                </Button>
            </Space>
        </Card>
    );
};

export default LLMSetupGuide;
