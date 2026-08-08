import React, { useState, useEffect } from 'react';
import { Card, Table, Form, Input, Button, Select, message, Popconfirm, Tag, Space } from 'antd';
import { DeleteOutlined, UserAddOutlined, TeamOutlined } from '@ant-design/icons';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Option } = Select;

interface WhitelistUser {
    username: string;
    gender: string;
}

const WhitelistManager: React.FC = () => {
    const [users, setUsers] = useState<WhitelistUser[]>([]);
    const [loading, setLoading] = useState(false);
    const [form] = Form.useForm();

    const fetchWhitelist = async () => {
        setLoading(true);
        try {
            const res = await axios.get(`${API_BASE_URL}/api/admin/whitelist`);
            // Parse users which can be string or dict
            const parsedUsers = res.data.users.map((u: any) => {
                if (typeof u === 'string') {
                    return { username: u, gender: 'male' }; // Default assumption
                }
                return u;
            });
            setUsers(parsedUsers);
        } catch (error: any) {
            message.error('加载白名单失败: ' + (error.response?.data?.detail || error.message));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchWhitelist();
    }, []);

    const handleAdd = async (values: any) => {
        try {
            await axios.post(`${API_BASE_URL}/api/admin/whitelist/user`, values);
            message.success('添加成功');
            form.resetFields();
            fetchWhitelist();
        } catch (error: any) {
            message.error('添加失败: ' + (error.response?.data?.detail || error.message));
        }
    };

    const handleDelete = async (username: string) => {
        try {
            await axios.delete(`${API_BASE_URL}/api/admin/whitelist/user/${username}`);
            message.success('删除成功');
            fetchWhitelist();
        } catch (error: any) {
            message.error('删除失败: ' + (error.response?.data?.detail || error.message));
        }
    };

    const columns = [
        {
            title: '用户名',
            dataIndex: 'username',
            key: 'username',
            render: (text: string) => <Space><UserAddOutlined />{text}</Space>,
        },
        {
            title: '性别',
            dataIndex: 'gender',
            key: 'gender',
            render: (text: string) => (
                <Tag color={text === 'female' ? 'magenta' : 'blue'}>
                    {text === 'female' ? '女性' : '男性'}
                </Tag>
            ),
        },
        {
            title: '操作',
            key: 'action',
            render: (_: any, record: WhitelistUser) => (
                <Popconfirm
                    title="确定要删除该用户吗?"
                    onConfirm={() => handleDelete(record.username)}
                    okText="确定"
                    cancelText="取消"
                >
                    <Button type="text" danger icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>
            ),
        },
    ];

    return (
        <Card title={<span><TeamOutlined /> 白名单管理</span>} variant="borderless">
            <Form
                form={form}
                layout="inline"
                onFinish={handleAdd}
                style={{ marginBottom: 24 }}
            >
                <Form.Item
                    name="username"
                    rules={[{ required: true, message: '请输入用户名' }]}
                >
                    <Input placeholder="用户名" prefix={<UserAddOutlined />} />
                </Form.Item>
                <Form.Item
                    name="gender"
                    initialValue="male"
                >
                    <Select style={{ width: 100 }}>
                        <Option value="male">男性</Option>
                        <Option value="female">女性</Option>
                    </Select>
                </Form.Item>
                <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading}>
                        添加用户
                    </Button>
                </Form.Item>
            </Form>

            <Table
                columns={columns}
                dataSource={users}
                rowKey="username"
                loading={loading}
                pagination={{ pageSize: 10 }}
            />
        </Card>
    );
};

export default WhitelistManager;
