import React, { useState, useEffect } from 'react';
import { Card, Button, message, Spin, Alert, Typography, Input, Space, Select } from 'antd';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Text, Paragraph, Link } = Typography;

const UserLLMConfig: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const [savingKeys, setSavingKeys] = useState(false);

    const [keyStatus, setKeyStatus] = useState<Record<string, boolean>>({});
    const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});

    const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1');
    const [modelName, setModelName] = useState('gpt-4o');

    // 模型列表
    const [models, setModels] = useState<string[]>([]);
    const [fetchingModels, setFetchingModels] = useState(false);

    const fetchKeyStatus = async () => {
        try {
            const res = await axios.get(`${API_BASE_URL}/api/config/llm_keys`);
            setKeyStatus(res.data || {});
        } catch (e) { /* ignore */ }
    };

    const fetchCurrentConfig = async () => {
        try {
            const st = await axios.get(`${API_BASE_URL}/api/config/llm_status`);
            if (st.data?.base_url) setBaseUrl(st.data.base_url);
            if (st.data?.model_name) setModelName(st.data.model_name);
        } catch (e) { /* ignore */ }
    };

    useEffect(() => {
        const init = async () => {
            setLoading(true);
            try { await Promise.all([fetchKeyStatus(), fetchCurrentConfig()]); } finally { setLoading(false); }
        };
        init();
    }, []);

    const handleFetchModels = async () => {
        const currentBaseUrl = baseUrl?.trim();
        const currentApiKey = keyInputs['OPENAI_API_KEY']?.trim() || (keyStatus['OPENAI_API_KEY'] ? '' : '');
        if (!currentBaseUrl) { message.warning('请先填入 Base URL'); return; }
        if (!currentApiKey) { message.warning('请先填入 API Key'); return; }

        setFetchingModels(true);
        try {
            const url = currentBaseUrl.replace(/\/+$/, '') + '/models';
            const resp = await axios.get(url, {
                headers: { Authorization: `Bearer ${currentApiKey}` },
                timeout: 15000,
            });
            const data = resp.data?.data || [];
            const ids: string[] = data
                .map((m: any) => m.id)
                .filter((id: string) => id && typeof id === 'string')
                .sort();
            if (ids.length === 0) {
                message.warning('未获取到模型列表，请检查 Base URL 和 API Key');
            } else {
                setModels(ids);
                message.success(`获取到 ${ids.length} 个模型`);
                if (!ids.includes(modelName)) setModelName(ids[0]);
            }
        } catch (e: any) {
            const detail = e?.response?.data?.error?.message || e?.message || '请求失败';
            message.error(`获取模型列表失败: ${detail}`);
        } finally {
            setFetchingModels(false);
        }
    };

    const handleSaveKeys = async () => {
        const payload: Record<string, string> = {};

        const inputKey = keyInputs['OPENAI_API_KEY'];
        if (inputKey?.trim()) payload['OPENAI_API_KEY'] = inputKey.trim();
        if (baseUrl?.trim()) payload['OPENAI_BASE_URL'] = baseUrl.trim();
        if (modelName?.trim()) payload['LLM_MODEL_NAME'] = modelName.trim();

        const searchKey = keyInputs['HUAWEI_SEARCH_API_KEY'];
        if (searchKey?.trim()) payload['HUAWEI_SEARCH_API_KEY'] = searchKey.trim();

        if (!payload['OPENAI_API_KEY'] && !payload['OPENAI_BASE_URL'] && !payload['LLM_MODEL_NAME']) {
            message.warning('请先填入配置'); return;
        }

        setSavingKeys(true);
        try {
            const res = await axios.post(`${API_BASE_URL}/api/config/llm_keys`, payload);
            const verdicts: Record<string, any> = res.data?.verification || {};
            const unverified = Object.entries(verdicts).filter(([, v]) => v?.status === 'unverified');
            if (unverified.length > 0) {
                message.warning(String(unverified[0][1]?.reason || '未能校验密钥，已按有效保存'));
            } else {
                const names = Object.keys(verdicts).map((k) => k.replace('_API_KEY', '')).join('、');
                message.success(`${names || '配置'} 校验通过并已生效`);
            }
            setKeyInputs({});
            await fetchKeyStatus();
            await fetchCurrentConfig();
        } catch (e: any) {
            message.error(String(e?.response?.data?.detail || '配置保存失败'));
        } finally {
            setSavingKeys(false);
        }
    };

    if (loading) return <Spin />;

    return (
        <div style={{ maxWidth: 600 }}>
            <Card title="LLM 模型配置" style={{ marginBottom: 24 }}>
                <Alert type="info" showIcon style={{ marginBottom: 20 }}
                    message="OpenAI 兼容接口"
                    description="支持所有提供 OpenAI 兼容 API 的服务商。填入 Base URL 和 API Key 后可获取模型列表。" />

                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <div>
                        <Text strong>接口地址（Base URL）</Text>
                        <Input style={{ marginTop: 8 }}
                            placeholder="https://api.openai.com/v1"
                            value={baseUrl}
                            onChange={(e) => { setBaseUrl(e.target.value); setModels([]); }} />
                        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                            服务商的 OpenAI 兼容 API 地址，必须以 /v1 结尾
                        </Paragraph>
                    </div>

                    <div>
                        <Text strong>API Key</Text>
                        <Input.Password style={{ marginTop: 8 }}
                            placeholder={keyStatus['OPENAI_API_KEY'] ? '已配置（留空则不修改）' : 'sk-...'}
                            value={keyInputs['OPENAI_API_KEY'] || ''}
                            onChange={(e) => { setKeyInputs({ ...keyInputs, OPENAI_API_KEY: e.target.value }); setModels([]); }} />
                        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                            密钥只保存在本机，不会上传到任何服务器
                        </Paragraph>
                    </div>

                    <div>
                        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                            <Text strong>模型名称</Text>
                            <Button size="small" loading={fetchingModels} onClick={handleFetchModels}
                                disabled={!baseUrl?.trim()}>
                                获取模型列表
                            </Button>
                        </Space>
                        {models.length > 0 ? (
                            <Select
                                showSearch
                                style={{ width: '100%', marginTop: 8 }}
                                placeholder="选择模型"
                                value={modelName}
                                onChange={(v) => setModelName(v)}
                                options={models.map((m) => ({ value: m, label: m }))}
                                filterOption={(input, option) =>
                                    (option?.label as string)?.toLowerCase().includes(input.toLowerCase())
                                }
                            />
                        ) : (
                            <Input style={{ marginTop: 8 }}
                                placeholder="gpt-4o / deepseek-chat / qwen-plus ..."
                                value={modelName}
                                onChange={(e) => setModelName(e.target.value)} />
                        )}
                        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                            {models.length > 0
                                ? `共 ${models.length} 个可用模型，支持搜索过滤`
                                : '手动输入模型名，或点击"获取模型列表"从接口拉取'}
                        </Paragraph>
                    </div>

                    <div>
                        <Text strong>联网搜索 API Key（可选）</Text>
                        <Input.Password style={{ marginTop: 8 }}
                            placeholder={keyStatus['HUAWEI_SEARCH_API_KEY'] ? '已配置（留空则不修改）' : '粘贴搜索 API Key'}
                            value={keyInputs['HUAWEI_SEARCH_API_KEY'] || ''}
                            onChange={(e) => setKeyInputs({ ...keyInputs, HUAWEI_SEARCH_API_KEY: e.target.value })} />
                        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                            <Link href="https://console.huaweicloud.com/csb/" target="_blank" rel="noreferrer">前往申请华为云搜索服务</Link>
                        </Paragraph>
                    </div>

                    <Button onClick={handleSaveKeys} loading={savingKeys} type="primary" block size="large">
                        {savingKeys ? '正在校验…' : '保存并校验'}
                    </Button>
                </Space>
            </Card>
        </div>
    );
};

export default UserLLMConfig;
