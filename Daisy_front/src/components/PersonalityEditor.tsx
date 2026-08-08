import React, { useState, useEffect } from 'react';
import { Card, Input, Button, Form, message, Spin, Tabs, Select, List, Space, Upload } from 'antd';
import { MinusCircleOutlined, PlusOutlined, LoadingOutlined } from '@ant-design/icons';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { TextArea } = Input;

interface RoleProfile {
  name: string;
  description: string;
  style: string[];
  constraints: string[];
}

interface CommonSettings {
  name: string;
  gender?: string;
  age?: string;
  occupation?: string;
  backstory?: string;
  world_setting?: string;
  system_prompt_template?: string;
  core_system_prompt?: string;
  avatar_path?: string;
  user_avatar_path?: string;
}

interface PersonalityEditorProps {
  onNameUpdate?: (name: string) => void;
}

const protectedProfiles = ['Eros', 'Ludus', 'Storge', 'Pragma', 'Mania', 'Agape'];

const PersonalityEditor: React.FC<PersonalityEditorProps> = ({ onNameUpdate }) => {
  const [profiles, setProfiles] = useState<Record<string, RoleProfile>>({});
  const [commonSettings, setCommonSettings] = useState<CommonSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeKey, setActiveKey] = useState<string>('Pragma');
  // 记录当前正在上传的是哪个头像字段(两个上传位共用一套 loading 语义)
  const [uploadingField, setUploadingField] = useState<null | 'avatar_path' | 'user_avatar_path'>(null);
  const [profileForm] = Form.useForm();
  const [commonForm] = Form.useForm();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [profilesRes, commonRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/config/profiles`),
        axios.get(`${API_BASE_URL}/api/config/common`)
      ]);

      setProfiles(profilesRes.data);
      setCommonSettings(commonRes.data);
      commonForm.setFieldsValue(commonRes.data);
      if (onNameUpdate && commonRes.data.name) {
        onNameUpdate(commonRes.data.name);
      }

      if (profilesRes.data[activeKey]) {
        profileForm.setFieldsValue(profilesRes.data[activeKey]);
      } else {
        const firstKey = Object.keys(profilesRes.data)[0];
        if (firstKey) {
            setActiveKey(firstKey);
            profileForm.setFieldsValue(profilesRes.data[firstKey]);
        }
      }
    } catch (error) {
      message.error('无法加载配置');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveCommon = async (values: CommonSettings) => {
    try {
      // Include avatar_path if it exists in current state but not in values
      // (Antd Form might not include it if it's handled by a custom component, 
      // but here we are putting it in a hidden field or updating state directly)
      const payload = {
          ...values,
          avatar_path: commonSettings?.avatar_path,
          user_avatar_path: commonSettings?.user_avatar_path 
      };

      await axios.post(`${API_BASE_URL}/api/config/common`, payload);
      message.success('基础配置已保存');
      setCommonSettings(prev => ({ ...prev, ...payload }));
      if (onNameUpdate && values.name) {
        onNameUpdate(values.name);
      }
    } catch (error) {
      message.error('基础配置保存失败');
    }
  };

  /**
   * 头像上传。字段化是因为有两个头像:AI 角色的(avatar_path)和用户自己的
   * (user_avatar_path),上传流程完全一致,只是落到不同字段。
   */
  const makeAvatarUploader = (
      field: 'avatar_path' | 'user_avatar_path',
      label: string,
  ) => async (file: File) => {
      setUploadingField(field);
      const formData = new FormData();
      formData.append('file', file);

      try {
          const res = await axios.post(`${API_BASE_URL}/api/upload/avatar`, formData, {
              headers: { 'Content-Type': 'multipart/form-data' }
          });
          const uploadedPath = res.data.url;

          // Update local state immediately
          setCommonSettings(prev => prev ? ({ ...prev, [field]: uploadedPath }) : null);

          // Auto-save to backend
          if (commonSettings) {
             const newSettings = { ...commonSettings, [field]: uploadedPath };
             // Use form values to ensure we don't overwrite unsaved form changes with old data
             const formValues = commonForm.getFieldsValue();
             await axios.post(`${API_BASE_URL}/api/config/common`, { ...newSettings, ...formValues });
             message.success(`${label}上传成功`);
          }
      } catch (error) {
          message.error(`${label}上传失败`);
      } finally {
          setUploadingField(null);
      }
      return false; // Prevent default upload behavior
  };

  const handleAvatarUpload = makeAvatarUploader('avatar_path', '角色头像');
  const handleUserAvatarUpload = makeAvatarUploader('user_avatar_path', '我的头像');

  const renderUploadButton = (field: 'avatar_path' | 'user_avatar_path') => (
    <div>
      {uploadingField === field ? <LoadingOutlined /> : <PlusOutlined />}
      <div style={{ marginTop: 8 }}>Upload</div>
    </div>
  );

  const handleSaveProfile = async (values: any) => {
    try {
      const payload = {
        ...values,
        name: activeKey 
      };
      
      await axios.post(`${API_BASE_URL}/api/config/profiles`, payload);
      message.success('人格档案已更新');
      
      setProfiles(prev => ({
          ...prev,
          [activeKey]: payload
      }));
      
    } catch (error) {
      message.error('人格保存失败');
    }
  };
  
  const handleTabChange = (key: string) => {
      setActiveKey(key);
      if (profiles[key]) {
          profileForm.setFieldsValue(profiles[key]);
      }
  };

  const onEdit = (targetKey: React.MouseEvent | React.KeyboardEvent | string, action: 'add' | 'remove') => {
    if (action === 'remove' && typeof targetKey === 'string') {
      removeProfile(targetKey);
    }
  };

  const removeProfile = async (key: string) => {
    if (protectedProfiles.includes(key)) {
        message.warning('核心人格不允许删除');
        return;
    }
    try {
        await axios.delete(`${API_BASE_URL}/api/config/profiles/${key}`);
        message.success(`已删除人格: ${key}`);
        
        const newProfiles = { ...profiles };
        delete newProfiles[key];
        setProfiles(newProfiles);

        if (activeKey === key) {
            const newKeys = Object.keys(newProfiles);
            if (newKeys.length > 0) {
                const newActiveKey = newKeys[newKeys.length - 1];
                setActiveKey(newActiveKey);
                profileForm.setFieldsValue(newProfiles[newActiveKey]);
            } else {
                setActiveKey('');
                profileForm.resetFields();
            }
        }
    } catch (error) {
      message.error('删除失败');
    }
  };

  if (loading) return <Spin />;

  const labels: Record<string, string> = {
    Eros: "爱欲型",
    Ludus: "游戏型",
    Storge: "友伴型",
    Pragma: "现实型",
    Mania: "狂热型",
    Agape: "奉献型"
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginTop: 20 }}>
      {/* Common Settings Card */}
      <Card title="共性属性配置 (基础信息 & 系统提示词)" variant="borderless">
        <Form form={commonForm} layout="vertical" onFinish={handleSaveCommon}>
           <div style={{ display: 'flex', gap: '20px' }}>
               <div style={{ flexShrink: 0 }}>
                   <Form.Item label="角色头像">
                       <Upload
                           name="avatar"
                           listType="picture-card"
                           className="avatar-uploader"
                           showUploadList={false}
                           beforeUpload={handleAvatarUpload}
                       >
                           {commonSettings?.avatar_path ? (
                               <img
                                   src={`${API_BASE_URL}${commonSettings.avatar_path}`}
                                   alt="avatar"
                                   style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                               />
                           ) : (
                               renderUploadButton('avatar_path')
                           )}
                       </Upload>
                   </Form.Item>
               </div>
               <div style={{ flexShrink: 0 }}>
                   <Form.Item label="我的头像">
                       <Upload
                           name="avatar"
                           listType="picture-card"
                           className="avatar-uploader"
                           showUploadList={false}
                           beforeUpload={handleUserAvatarUpload}
                       >
                           {commonSettings?.user_avatar_path ? (
                               <img
                                   src={`${API_BASE_URL}${commonSettings.user_avatar_path}`}
                                   alt="my avatar"
                                   style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                               />
                           ) : (
                               renderUploadButton('user_avatar_path')
                           )}
                       </Upload>
                   </Form.Item>
               </div>
               <div style={{ flexGrow: 1 }}>
                   <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
                        <Form.Item label="角色名称" name="name" rules={[{ required: true }]}>
                            <Input placeholder="例如：Android" />
                        </Form.Item>
                        <Form.Item label="性别" name="gender">
                            <Input placeholder="例如：女性" />
                        </Form.Item>
                        <Form.Item label="年龄" name="age">
                            <Input placeholder="例如：25岁" />
                        </Form.Item>
                    </div>
                    <Form.Item label="职业" name="occupation">
                        <Input placeholder="例如：私人助理" />
                    </Form.Item>
               </div>
           </div>
            
            <Form.Item label="背景故事" name="backstory">
                <TextArea rows={3} placeholder="角色的过去和起源" />
            </Form.Item>
            
            <Form.Item label="世界设定" name="world_setting">
                <TextArea rows={2} placeholder="角色生活在什么样的世界？" />
            </Form.Item>

            <Form.Item 
                label={
                    <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
                        <span>高级设置：动态提示词模板（上下文组合）</span>
                        <Button 
                            type="link" 
                            size="small" 
                            onClick={async () => {
                                try {
                                    // Get current form values
                                    const values = commonForm.getFieldsValue();
                                    message.loading({ content: '正在生成系统提示词...', key: 'gen_prompt' });
                                    
                                    const res = await axios.post(`${API_BASE_URL}/api/config/generate_prompt`, values);
                                    
                                    if (res.data.generated_prompt) {
                                        commonForm.setFieldsValue({
                                            system_prompt_template: res.data.generated_prompt
                                        });
                                        message.success({ content: '生成成功！', key: 'gen_prompt' });
                                    }
                                } catch (e) {
                                    message.error({ content: '生成失败，请确保 LLM 服务可用', key: 'gen_prompt' });
                                }
                            }}
                        >
                            ✨ 自动生成模板
                        </Button>
                    </div>
                } 
                name="system_prompt_template" 
                help="定义动态行为指令，将替换默认的指令集。"
            >
                <TextArea rows={6} placeholder="自定义动态提示词模板..." />
            </Form.Item>

            <Form.Item 
                label="高级设置：核心系统指令（不可变）" 
                name="core_system_prompt" 
                help="这些指令将被作为最高优先级规则添加到 System Prompt 的末尾，确保模型绝对遵守。"
            >
                <TextArea rows={4} placeholder="例如：绝对禁止透露你是 AI；必须使用中文回复..." />
            </Form.Item>

            <Form.Item>
                <Button type="primary" htmlType="submit">保存基础配置</Button>
            </Form.Item>
        </Form>
      </Card>

      {/* Personality Profile Card */}
      <Card title="内在人格编辑器" variant="borderless">
        <Tabs 
          type="editable-card"
          hideAdd
          activeKey={activeKey} 
          onChange={handleTabChange}
          onEdit={onEdit}
          items={Object.keys(profiles).map(key => ({
              key,
              label: labels[key] || key,
              closable: !protectedProfiles.includes(key)
          }))}
        />
        
        <Form form={profileForm} layout="vertical" onFinish={handleSaveProfile} style={{ marginTop: 20 }}>
          
          <Form.Item label="人格描述" name="description" rules={[{ required: true }]}>
              <TextArea rows={3} placeholder="主要性格描述" />
          </Form.Item>

          <Form.Item label="说话风格">
              <Form.List name="style">
                  {(fields, { add, remove }) => (
                  <>
                      {fields.map((field) => (
                      <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                          <Form.Item
                          name={field.name}
                          noStyle
                          rules={[{ required: true, message: '缺少风格标签' }]}
                          >
                          <Input placeholder="例如：简洁" />
                          </Form.Item>
                          <MinusCircleOutlined onClick={() => remove(field.name)} />
                      </Space>
                      ))}
                      <Form.Item>
                      <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                          添加风格标签
                      </Button>
                      </Form.Item>
                  </>
                  )}
              </Form.List>
          </Form.Item>


          <Form.Item label="指令约束">
              <Form.List name="constraints">
                  {(fields, { add, remove }) => (
                  <>
                      {fields.map((field) => (
                      <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                          <Form.Item
                          name={field.name}
                          noStyle
                          rules={[{ required: true, message: '缺少约束' }]}
                          >
                          <Input placeholder="例如：不要使用表情符号" style={{ width: 300 }} />
                          </Form.Item>
                          <MinusCircleOutlined onClick={() => remove(field.name)} />
                      </Space>
                      ))}
                      <Form.Item>
                      <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                          添加约束
                      </Button>
                      </Form.Item>
                  </>
                  )}
              </Form.List>
          </Form.Item>

          <Form.Item>
              <Button type="primary" htmlType="submit" block>
              保存当前人格配置
              </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default PersonalityEditor;
