import React, { useState } from 'react';
import { Card, Form, Input, Button, Tabs, message, Typography } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Title } = Typography;

interface AuthProps {
    onLogin: (token: string, username: string, isSuperUser: boolean) => void;
}

const Auth: React.FC<AuthProps> = ({ onLogin }) => {
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('login');

    const onFinishLogin = async (values: any) => {
        setLoading(true);
        try {
            // Note: FastAPI OAuth2PasswordRequestForm expects form-data, not JSON
            const formData = new FormData();
            formData.append('username', values.username);
            formData.append('password', values.password);

            const res = await axios.post(`${API_BASE_URL}/api/auth/login`, formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            
            message.success('登录成功');
            onLogin(res.data.access_token, values.username, res.data.is_superuser);
        } catch (error: any) {
            message.error(error.response?.data?.detail || '登录失败');
        } finally {
            setLoading(false);
        }
    };

    const onFinishRegister = async (values: any) => {
        setLoading(true);
        try {
            await axios.post(`${API_BASE_URL}/api/auth/register`, {
                username: values.username,
                password: values.password
            });
            message.success('注册成功，请登录');
            setActiveTab('login');
        } catch (error: any) {
            message.error(error.response?.data?.detail || '注册失败');
        } finally {
            setLoading(false);
        }
    };

    const LoginForm = () => (
        <Form
            name="login_form"
            onFinish={onFinishLogin}
            layout="vertical"
        >
            <Form.Item
                name="username"
                rules={[{ required: true, message: '请输入用户名' }]}
            >
                <Input prefix={<UserOutlined />} placeholder="用户名" size="large" />
            </Form.Item>
            <Form.Item
                name="password"
                rules={[{ required: true, message: '请输入密码' }]}
            >
                <Input.Password prefix={<LockOutlined />} placeholder="密码" size="large" />
            </Form.Item>
            <Form.Item>
                <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                    登录
                </Button>
            </Form.Item>
        </Form>
    );

    const RegisterForm = () => (
        <Form
            name="register_form"
            onFinish={onFinishRegister}
            layout="vertical"
        >
            <Form.Item
                name="username"
                rules={[{ required: true, message: '请输入用户名' }]}
            >
                <Input prefix={<UserOutlined />} placeholder="设置用户名" size="large" />
            </Form.Item>
            <Form.Item
                name="password"
                rules={[
                    { required: true, message: '请输入密码' },
                    { min: 8, message: '密码至少8位' },
                    { pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/, message: '密码需包含大小写字母、数字和特殊字符' }
                ]}
            >
                <Input.Password prefix={<LockOutlined />} placeholder="设置密码" size="large" />
            </Form.Item>
            <Form.Item
                name="confirm"
                dependencies={['password']}
                hasFeedback
                rules={[
                    { required: true, message: '请确认密码' },
                    ({ getFieldValue }) => ({
                        validator(_, value) {
                            if (!value || getFieldValue('password') === value) {
                                return Promise.resolve();
                            }
                            return Promise.reject(new Error('两次输入的密码不一致'));
                        },
                    }),
                ]}
            >
                <Input.Password prefix={<LockOutlined />} placeholder="确认密码" size="large" />
            </Form.Item>
            <Form.Item>
                <Button type="primary" htmlType="submit" block size="large" loading={loading}>
                    注册
                </Button>
            </Form.Item>
        </Form>
    );

    const items = [
        { key: 'login', label: '登录', children: <LoginForm /> },
        { key: 'register', label: '注册', children: <RegisterForm /> },
    ];

    return (
        <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            alignItems: 'center', 
            minHeight: '100vh', 
            background: '#f0f2f5' 
        }}>
            <Card style={{ width: 400, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                <div style={{ textAlign: 'center', marginBottom: 24 }}>
                    <Title level={3}>Whisper</Title>
                </div>
                <Tabs activeKey={activeTab} onChange={setActiveTab} items={items} centered />
            </Card>
        </div>
    );
};

export default Auth;
