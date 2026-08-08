import React, { useState } from 'react';
import { Card, Input, Button, Typography, Alert, Space } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Title, Paragraph, Text } = Typography;

interface Props {
    onUnlocked: (token: string, isSuperUser: boolean) => void;
}

/**
 * 本地隐私锁的解锁界面。
 *
 * 这不是"登录" —— 没有账号、没有服务器、没有找回密码。它只是一道本机的门:
 * 数据一直在你的电脑上,这道锁决定"能开这台电脑的人是否都能翻看这些对话"。
 *
 * 关键:输错密码只是**可重试**,绝不会把用户推到别的页面。
 * 上一版的事故正是"一次失败就落到被禁用的登录界面",成了死路。
 */
const LocalUnlock: React.FC<Props> = ({ onUnlocked }) => {
    const [password, setPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const submit = async () => {
        if (!password) {
            setError('请输入密码');
            return;
        }
        setLoading(true);
        setError(null);
        try {
            const res = await axios.post(`${API_BASE_URL}/api/auth/local_session`, { password });
            if (res.data?.access_token) {
                onUnlocked(res.data.access_token, Boolean(res.data.is_superuser));
                return;
            }
            setError('解锁失败,请重试');
        } catch (e: any) {
            // 停留在本页重试即可 —— 不跳转、不清状态
            setError(e?.response?.status === 401 ? '密码不正确' : '解锁失败,请重试');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            height: '100vh', display: 'flex',
            alignItems: 'center', justifyContent: 'center', background: '#f5f5f5',
        }}>
            <Card style={{ width: 400 }}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <div style={{ textAlign: 'center' }}>
                        <LockOutlined style={{ fontSize: 36, color: '#1677ff' }} />
                        <Title level={4} style={{ marginTop: 12, marginBottom: 4 }}>已锁定</Title>
                        <Text type="secondary">输入本机密码以继续</Text>
                    </div>

                    {error && <Alert type="error" showIcon message={error} />}

                    <Input.Password
                        autoFocus
                        placeholder="本机密码"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onPressEnter={submit}
                    />

                    <Button type="primary" block size="large" loading={loading} onClick={submit}>
                        解锁
                    </Button>

                    <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
                        这道锁只保护本机数据,密码不会上传,也**无法找回**。
                        忘记密码时只能删除应用数据目录重来(对话记录会一并丢失)。
                    </Paragraph>
                </Space>
            </Card>
        </div>
    );
};

export default LocalUnlock;
