
import React, { useState, useEffect } from 'react';
import { Card, Form, Button, Select, message, Spin, Alert, Typography, Divider, Switch, InputNumber, Radio, Input, Collapse } from 'antd';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Option } = Select;
const { Text } = Typography;

interface CommonSettings {
  llm_provider?: string;
  // llm_api_key?: string; // 已移除
  // llm_base_url?: string; // 已移除
  // llm_model_name?: string; // 已移除
  [key: string]: any;
}

interface ProviderConfig {
    name: string;
    provider: string;
    description: string;
    base_url?: string;
    model?: string;
}

const UserLLMConfig: React.FC = () => {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [initialSettings, setInitialSettings] = useState<CommonSettings | null>(null);
  const [availableProviders, setAvailableProviders] = useState<Record<string, ProviderConfig>>({});
  // 系统级 API Key:keyStatus 只记录"是否已配置"(后端不回传明文),keyInputs 是待保存的输入
  const [keyStatus, setKeyStatus] = useState<Record<string, boolean>>({});
  const [keyInputs, setKeyInputs] = useState<Record<string, string>>({});
  const [savingKeys, setSavingKeys] = useState(false);

  const fetchKeyStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/config/llm_keys`);
      setKeyStatus(res.data || {});
    } catch (e) {
      // 非管理员或接口不可用时不阻塞页面其余部分
    }
  };

  const handleSaveKeys = async () => {
    const payload: Record<string, string> = {};
    Object.entries(keyInputs).forEach(([k, v]) => {
      if (v && v.trim()) payload[k] = v.trim();
    });
    if (Object.keys(payload).length === 0) {
      message.warning('请先填入至少一个 API Key');
      return;
    }
    setSavingKeys(true);
    try {
      // 后端会先探活再落盘:填错服务的密钥当场 400,而不是等到用到时才失败
      const res = await axios.post(`${API_BASE_URL}/api/config/llm_keys`, payload);
      const verdicts: Record<string, any> = res.data?.verification || {};
      const unverified = Object.entries(verdicts).filter(([, v]) => v?.status === 'unverified');
      if (unverified.length > 0) {
        // 网络不通/服务商抖动时后端放行,但要如实告知没验成功
        message.warning(String(unverified[0][1]?.reason || '未能校验密钥,已按有效保存'));
      } else {
        const names = Object.keys(verdicts).map((k) => k.replace('_API_KEY', '')).join('、');
        message.success(`${names || 'API Key'} 校验通过并已生效`);
      }
      setKeyInputs({});
      await fetchKeyStatus();
    } catch (e: any) {
      message.error(String(e?.response?.data?.detail || 'API Key 保存失败'));
    } finally {
      setSavingKeys(false);
    }
  };
  
  // ... (useEffect remains same)

  const handleProviderChange = (e: any) => {
      const providerKey = e.target.value;
      const providerConfig = availableProviders[providerKey];
      if (providerConfig) {
          form.setFieldsValue({
              llm_provider: providerKey,
              llm_base_url: providerConfig.base_url,
              llm_model_name: providerConfig.model,
              llm_api_key: undefined // Clear API Key on provider switch to avoid mismatch
          });
      }
  };

  const handleCardClick = (providerKey: string) => {
      const providerConfig = availableProviders[providerKey];
      if (providerConfig) {
          form.setFieldsValue({
              llm_provider: providerKey,
              llm_base_url: providerConfig.base_url,
              llm_model_name: providerConfig.model,
              llm_api_key: undefined
          });
      }
  };

  
  useEffect(() => {
    const init = async () => {
        setLoading(true);
        try {
            await Promise.all([fetchProviders(), fetchSettings(), fetchKeyStatus()]);
        } finally {
            setLoading(false);
        }
    };
    init();
  }, []);

  const fetchProviders = async () => {
      try {
          const res = await axios.get(`${API_BASE_URL}/api/config/providers`);
          setAvailableProviders(res.data);
      } catch (error) {
          console.error("Failed to fetch providers", error);
      }
  };

  const fetchSettings = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/config/common`);
      setInitialSettings(res.data);
      
      // 默认选中第一个可用的 provider，如果未设置
      let defaultProvider = res.data.llm_provider;
      
      form.setFieldsValue({
          llm_provider: defaultProvider || 'huaweicloud',
          
          // Embedding Settings (保留，但也建议未来移至后端配置)
          embedding_provider: res.data.embedding_provider || 'siliconflow',
          embedding_model_name: res.data.embedding_model_name || 'BAAI/bge-large-zh-v1.5',
          
          // Local LLM Settings
          local_llm_use_gpu: res.data.local_llm_use_gpu,
          local_llm_gpu_id: res.data.local_llm_gpu_id || 0,
          task_summarize_use_local: res.data.task_summarize_use_local
      });

    } catch (error) {
      console.error(error);
      message.error('无法加载配置');
    }
  };

  const handleSave = async (values: any) => {
    if (!initialSettings) return;
    
    setLoading(true);
    try {
      // 仅发送 provider 名称，后端负责加载具体配置
      // 但如果用户填了高级设置，也一并发送
      const payload = {
          ...initialSettings,
          ...values,
      };
      
      // 过滤掉 undefined 或空字符串的字段，避免覆盖后端配置（虽然后端也有防范）
      if (!values.llm_api_key) delete payload.llm_api_key;
      if (!values.llm_base_url) delete payload.llm_base_url;
      if (!values.llm_model_name) delete payload.llm_model_name;
      
      await axios.post(`${API_BASE_URL}/api/config/common`, payload);
      message.success('大模型配置已保存');
      setInitialSettings(payload);
    } catch (error) {
      message.error('配置保存失败');
    } finally {
        setLoading(false);
    }
  };

  if (loading && !initialSettings) return <Spin style={{ display: 'block', margin: '20px auto' }} />;

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: 24 }}>
        <Card title="大模型配置 (Model Settings)">
        <Alert
            message="API Key 保存在本机"
            description="本应用不内置任何密钥。在下方填入你自己的 API Key,它会写入本机配置并立即对全部功能生效(包括情绪分析、记忆检索等内部环节)。"
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
        />

        {/* 系统级密钥:写入 /api/config/llm_keys,热重载所有 provider。
            这与下方"调试设置"里的用户级 llm_api_key 不同 —— 后者只影响最终回复生成,
            工作流内的路由/记忆/策略等 agent 用的是系统级配置。 */}
        <Card
            type="inner"
            title="API Key"
            style={{ marginBottom: 24 }}
            extra={<Text type="secondary" style={{ fontSize: 12 }}>
                {Object.entries(keyStatus).filter(([, v]) => v).length > 0
                    ? `已配置: ${Object.entries(keyStatus).filter(([, v]) => v).map(([k]) => k.replace('_API_KEY', '')).join(', ')}`
                    : '尚未配置'}
            </Text>}
        >
            <Form.Item label="华为云 ModelArts (MAAS_API_KEY)" style={{ marginBottom: 12 }}>
                <Input.Password
                    placeholder={keyStatus['MAAS_API_KEY'] ? '已配置(留空则不修改)' : '粘贴 API Key'}
                    value={keyInputs['MAAS_API_KEY'] || ''}
                    onChange={(e) => setKeyInputs({ ...keyInputs, MAAS_API_KEY: e.target.value })}
                />
            </Form.Item>
            <Form.Item label="硅基流动 SiliconFlow (SILICONFLOW_API_KEY)" style={{ marginBottom: 12 }}>
                <Input.Password
                    placeholder={keyStatus['SILICONFLOW_API_KEY'] ? '已配置(留空则不修改)' : '粘贴 API Key'}
                    value={keyInputs['SILICONFLOW_API_KEY'] || ''}
                    onChange={(e) => setKeyInputs({ ...keyInputs, SILICONFLOW_API_KEY: e.target.value })}
                />
            </Form.Item>
            {/* 搜索密钥此前没有任何配置入口,只能手改配置文件。
                而它缺失时联网搜索不可用 —— 现在与 LLM 密钥同等对待:同一个入口、
                同一套保存前探活(打的是搜索端点而非聊天端点)。 */}
            <Form.Item label="华为云联网搜索 (HUAWEI_SEARCH_API_KEY,可选:让她能查天气/新闻等实时信息)" style={{ marginBottom: 12 }}>
                <Input.Password
                    placeholder={keyStatus['HUAWEI_SEARCH_API_KEY'] ? '已配置(留空则不修改)' : '粘贴搜索 API Key'}
                    value={keyInputs['HUAWEI_SEARCH_API_KEY'] || ''}
                    onChange={(e) => setKeyInputs({ ...keyInputs, HUAWEI_SEARCH_API_KEY: e.target.value })}
                />
            </Form.Item>
            <Button onClick={handleSaveKeys} loading={savingKeys} type="primary" ghost>
                {savingKeys ? '正在校验密钥…' : '保存并校验 API Key'}
            </Button>
        </Card>
        
        <Form form={form} layout="vertical" onFinish={handleSave}>
            
            <Form.Item label="选择模型服务商 (Select Provider)" name="llm_provider" rules={[{ required: true }]}>
                <Radio.Group style={{ width: '100%' }} onChange={handleProviderChange}>
                    {Object.values(availableProviders).map((provider: any) => (
                        <Card 
                            key={provider.provider}
                            hoverable 
                            style={{ marginBottom: 16 }}
                            styles={{ body: { padding: '12px' } }}
                            onClick={() => handleCardClick(provider.provider)}
                        >
                            <Radio value={provider.provider}>
                                <span style={{ fontWeight: 'bold' }}>{provider.name}</span>
                                <br/>
                                <Text type="secondary" style={{ fontSize: '12px', marginLeft: 24 }}>
                                    {provider.description}
                                </Text>
                            </Radio>
                        </Card>
                    ))}
                    {/* Fallback if no providers loaded or for legacy support if needed, though we want to enforce config */}
                    {Object.keys(availableProviders).length === 0 && (
                        <Alert message="无法加载模型列表，请检查后端配置。" type="error" />
                    )}
                </Radio.Group>
            </Form.Item>

            <Collapse
                ghost
                style={{ marginBottom: 24 }}
                items={[
                    {
                        key: '1',
                        label: '调试设置 (Debug Settings)',
                        children: (
                            <>
                                <Alert 
                                    message="开发者选项" 
                                    description="通常情况下，系统会自动从服务器环境变量加载配置。仅当您需要临时覆盖 API Key 或 Model 时使用。"
                                    type="info"
                                    showIcon
                                    style={{ marginBottom: 16 }}
                                />
                                <Form.Item label="Custom API Key (Optional)" name="llm_api_key">
                                    <Input.Password placeholder="Default: Loaded from server environment" />
                                </Form.Item>
                                <Form.Item label="Custom Base URL (Optional)" name="llm_base_url">
                                    <Input placeholder="Default: Provider default" />
                                </Form.Item>
                                <Form.Item label="Custom Model Name (Optional)" name="llm_model_name">
                                    <Input placeholder="Default: Provider default" />
                                </Form.Item>
                            </>
                        )
                    }
                ]}
            />

            <Form.Item>
                <Button type="primary" htmlType="submit" loading={loading} block size="large">
                    保存配置
                </Button>
            </Form.Item>
        </Form>
        </Card>
    </div>
  );
};

export default UserLLMConfig;
