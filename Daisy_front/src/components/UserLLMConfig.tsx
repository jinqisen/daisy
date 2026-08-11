import React, { useState, useEffect } from 'react';
import { Card, Form, Button, message, Spin, Alert, Typography, Input, Select, Space } from 'antd';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Text, Paragraph, Link } = Typography;

/** 预设模板 */
const PRESET_TEMPLATES: Record<string, { baseUrl: string; model: string; label: string }> = {
    openai: { baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o', label: 'OpenAI' },
    deepseek: { baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat', label: 'DeepSeek' },
    siliconflow: { baseUrl: 'https://api.siliconflow.cn/v1', model: 'Pro/deepseek-ai/DeepSeek-V3.2', label: '硅基流动 (SiliconFlow)' },
    qwen: { baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus', label: '通义千问 (阿里云)' },
    zhipu: { baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash', label: '智谱 GLM' },
    moonshot: { baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k', label: 'Moonshot (月之暗面)' },
    custom: { baseUrl: '', model: '', label: '自定义（手动输入）' },
};

const UserLLMConfig: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const [savingKeys, setSavingKeys] = useState(false);

    // 密钥状态
    const [keyStatus, setKeyStatus] = useState<Record<string, boolean>>({});
    const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});

    // 表单字段
    const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1');
    const [modelName, setModelName] = useState('gpt-4o');
    const [preset, setPreset] = useState('openai');

    const fetchKeyStatus = async () => {
        try {
            const res = await axios.get(`${API_BASE_URL}/api/config/llm_keys`);
            setKeyStatus(res.data || {});
        } catch (e) {
            // 非管理员或接口不可用时不影响页面
        }
    };

    const fetchCurrentConfig = async () => {
        try {
            const st = await axios.get(`${API_BASE_URL}/api/config/llm_status`);
            if (st.data?.base_url) setBaseUrl(st.data.base_url);
            if (st.data?.model_name) setModelName(st.data.model_name);
        } catch (e) {
            // 忽略
        }
    };

    useEffect(() => {
        const init = async () => {
            setLoading(true);
            try {
                await Promise.all([fetchKeyStatus(), fetchCurrentConfig()]);
            } finally {
                setLoading(false);
            }
        };
        init();
    }, []);

    const handlePresetChange = (key: string) => {
        setPreset(key);
        const tpl = PRESET_TEMPLATES[key];
        if (tpl && key !== 'custom') {
            setBaseUrl(tpl.baseUrl);
            setModelName(tpl.model);
        }
    };

    const handleSaveKeys = async () => {
        const payload: Record<string, string> = {};

        // API Key
        const inputKey = keyInputs['OPENAI_API_KEY'];
        if (inputKey && inputKey.trim()) {
            payload['OPENAI_API_KEY'] = inputKey.trim();
        }
        // Base URL
        if (baseUrl && baseUrl.trim()) {
            payload['OPENAI_BASE_URL'] = baseUrl.trim();
        }
        // Model Name
        if (modelName && modelName.trim()) {
            payload['LLM_MODEL_NAME'] = modelName.trim();
        }
        // Search Key
        const searchKey = keyInputs['HUAWEI_SEARCH_API_KEY'];
        if (searchKey && searchKey.trim()) {
            payload['HUAWEI_SEARCH_API_KEY'] = searchKey.trim();
        }

        if (!payload['OPENAI_API_KEY'] && !payload['OPENAI_BASE_URL'] && !payload['LLM_MODEL_NAME']) {
            message.warning('请先填入配置');
            return;
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

    const presetOptions = Object.entries(PRESET_TEMPLATES).map(([k, v]) => ({
        value: k,
        label: v.label,
    }));

    return (
        <div style={{ maxWidth: 600 }}>
            <Card title="LLM 模型配置" style={{ marginBottom: 24 }}>
                <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 20 }}
                    message="OpenAI 兼容接口"
                    description="支持所有提供 OpenAI 兼容 API 的服务商（OpenAI、DeepSeek、通义千问、硅基流动、智谱等）。填入你的 Base URL、API Key 和模型名即可。"
                />

                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {/* 预设模板 */}
                    <div>
                        <Text strong>快速选择（可选）</Text>
                        <Select
                            value={preset}
                            onChange={handlePresetChange}
                            options={presetOptions}
                            style={{ width: '100%', marginTop: 8 }}
                        />
                    </div>

                    {/* Base URL */}
                    <div>
                        <Text strong>接口地址（Base URL）</Text>
                        <Input
                            style={{ marginTop: 8 }}
                            placeholder="https://api.openai.com/v1"
                            value={baseUrl}
                            onChange={(e) => { setBaseUrl(e.target.value); setPreset('custom'); }}
                        />
                        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                            服务商的 OpenAI 兼容 API 地址，必须以 /v1 结尾
                        </Paragraph>
                    </div>

                    {/* API Key */}
                    <div>
                        <Text strong>API Key</Text>
                        <Input.Password
                            style={{ marginTop: 8 }}
                            placeholder={keyStatus['OPENAI_API_KEY'] ? '已配置（留空则不修改）' : 'sk-...'}
                            value={keyInputs['OPENAI_API_KEY'] || ''}
                            onChange={(e) => setKeyInputs({ ...keyInputs, OPENAI_API_KEY: e.target.value })}
                        />
                        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                            密钥只保存在本机，不会上传到任何服务器
                        </Paragraph>
                    </div>

                    {/* 模型名称 */}
                    <div>
                        <Text strong>模型名称</Text>
                        <Input
                            style={{ marginTop: 8 }}
                            placeholder="gpt-4o / deepseek-chat / qwen-plus ..."
                            value={modelName}
                            onChange={(e) => { setModelName(e.target.value); setPreset('custom'); }}
                        />
                        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
                            模型名称，如 gpt-4o、deepseek-v3.2、qwen-plus
                        </Paragraph>
                    </div>

                    {/* 联网搜索 */}
                    <div>
                        <Text strong>联网搜索 API Key（可选）</Text>
                        <Input.Password
                            style={{ marginTop: 8 }}
                            placeholder={keyStatus['HUAWEI_SEARCH_API_KEY'] ? '已配置（留空则不修改）' : '粘贴搜索 API Key'}
                            value={keyInputs['HUAWEI_SEARCH_API_KEY'] || ''}
                            onChange={(e) => setKeyInputs({ ...keyInputs, HUAWEI_SEARCH_API_KEY: e.target.value })}
                        />
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
