import React, { useState } from 'react';
import { Modal, Form, Input, message } from 'antd';
import axios from 'axios';
import { API_BASE_URL } from '../config';

interface ChangePasswordModalProps {
    visible: boolean;
    onCancel: () => void;
    onSuccess: () => void;
}

const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({ visible, onCancel, onSuccess }) => {
    const [form] = Form.useForm();
    const [loading, setLoading] = useState(false);

    const onFinish = async (values: any) => {
        setLoading(true);
        try {
            await axios.post(`${API_BASE_URL}/api/auth/change-password`, {
                old_password: values.oldPassword,
                new_password: values.newPassword
            });
            message.success('密码修改成功');
            form.resetFields();
            onSuccess();
        } catch (error: any) {
            message.error(error.response?.data?.detail || '密码修改失败');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Modal
            title="修改密码"
            open={visible}
            onCancel={onCancel}
            onOk={() => form.submit()}
            confirmLoading={loading}
            destroyOnHidden={true}
        >
            <Form
                form={form}
                layout="vertical"
                onFinish={onFinish}
            >
                <Form.Item
                    name="oldPassword"
                    label="当前密码"
                    rules={[{ required: true, message: '请输入当前密码' }]}
                >
                    <Input.Password placeholder="请输入当前密码" />
                </Form.Item>

                <Form.Item
                    name="newPassword"
                    label="新密码"
                    rules={[
                        { required: true, message: '请输入新密码' },
                        { min: 8, message: '密码长度至少8位' },
                        { pattern: /[A-Z]/, message: '需包含大写字母' },
                        { pattern: /[a-z]/, message: '需包含小写字母' },
                        { pattern: /\d/, message: '需包含数字' },
                        { pattern: /[ !@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?]/, message: '需包含特殊字符' }
                    ]}
                >
                    <Input.Password placeholder="请输入新密码 (需包含大小写字母、数字和特殊字符)" />
                </Form.Item>

                <Form.Item
                    name="confirmPassword"
                    label="确认新密码"
                    dependencies={['newPassword']}
                    rules={[
                        { required: true, message: '请确认新密码' },
                        ({ getFieldValue }) => ({
                            validator(_, value) {
                                if (!value || getFieldValue('newPassword') === value) {
                                    return Promise.resolve();
                                }
                                return Promise.reject(new Error('两次输入的密码不一致'));
                            },
                        }),
                    ]}
                >
                    <Input.Password placeholder="请再次输入新密码" />
                </Form.Item>
            </Form>
        </Modal>
    );
};

export default ChangePasswordModal;
