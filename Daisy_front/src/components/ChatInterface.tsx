import React, { useState, useEffect, useRef } from 'react';
import { Input, Button, Avatar, Typography, message, Collapse, Dropdown, MenuProps, Modal, Spin, Upload, Tooltip } from 'antd';
import { UserOutlined, RobotOutlined, SendOutlined, DownloadOutlined, EyeOutlined, ExclamationCircleFilled, LoadingOutlined, PoweroffOutlined, EllipsisOutlined, DownOutlined, PictureOutlined } from '@ant-design/icons';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { useChat } from '../hooks/useChat';
import LLMSetupGuide from './LLMSetupGuide';

const { TextArea } = Input;

interface ChatInterfaceProps {
  token?: string | null;
  onUnauthorized?: () => void;
  onStateUpdate: (data: any) => void;
  onHistoryLoad?: (data: any[]) => void;
  onSessionEnd: (duration: number, count: number) => void;
  aiName?: string;
  onConfigRequired?: () => void;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ token, onUnauthorized, onStateUpdate, onHistoryLoad, onSessionEnd, aiName = "Whisper", onConfigRequired }) => {
  const { messages, loading, isConnected, sessionId, sendMessage, startNewSession } = useChat({ 
      token,
      onUnauthorized,
      onStateUpdate,
      onHistoryLoad
  });

  const [input, setInput] = useState('');
  const [interactionCount, setInteractionCount] = useState(0);
  const [showNewMessageTip, setShowNewMessageTip] = useState(false);
  const [isCharacterReady, setIsCharacterReady] = useState<boolean>(true);
  // 角色卡未就绪的原因是否为"尚未配置模型"(与"正在生成"区分,见 checkCharacterStatus)
  const [needsLLMSetup, setNeedsLLMSetup] = useState<boolean>(false);
  const [characterStatusText, setCharacterStatusText] = useState<string>('');
  
  // Customization
  const [backgroundImage, setBackgroundImage] = useState<string | null>(null);
  const [avatarImage, setAvatarImage] = useState<string | null>(null);
  // 用户自己的头像(右侧气泡)。与 AI 角色头像是两个独立字段,别混用。
  const [userAvatarImage, setUserAvatarImage] = useState<string | null>(null);
  const [backgroundImageVersion, setBackgroundImageVersion] = useState<number>(0);

  const buildAssetUrl = (path: string | null, version: number) => {
    if (!path) {
      return undefined;
    }
    return `${API_BASE_URL}${path}${version ? `?v=${version}` : ''}`;
  };

  // Check character card status
  const checkCharacterStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/config/common`);
      if (res.data) {
        // If has_character_card is explicitly false, it means generating
        const isReady = res.data.has_character_card !== false;
        setIsCharacterReady(isReady);
        setCharacterStatusText(isReady ? 'Online' : 'Initializing...');

        // 角色卡未就绪时,需要区分两种截然不同的原因:
        //   1) 已配置模型,正在生成 → 显示加载动画
        //   2) 尚未配置模型(桌面版首次运行,包内不含 API Key)→ 引导用户去填密钥
        // 若不区分,第 2 种情况会永远转圈:生成需要密钥,而用户又被遮罩挡住无法填密钥。
        if (!isReady) {
            try {
                const st = await axios.get(`${API_BASE_URL}/api/config/llm_status`);
                setNeedsLLMSetup(st.data?.configured === false);
            } catch (e) {
                // 状态查询失败时不误判为"未配置",保持加载态
            }
        } else {
            setNeedsLLMSetup(false);
        }
        
        // Update customization
        if (res.data.background_image_path) {
            setBackgroundImage(res.data.background_image_path);
        }
        if (res.data.avatar_path) {
            setAvatarImage(res.data.avatar_path);
        }
        if (res.data.user_avatar_path) {
            setUserAvatarImage(res.data.user_avatar_path);
        }
        if (res.data.name) {
            document.title = res.data.name;
        }

        // Update full screen loading
        return isReady;
      }
    } catch (e) {
      console.error("Failed to check status", e);
      // 请求失败(401 竞态、后端刚启动等)不等于"系统错误"。
      // 桌面版首次运行必然处于未配置状态,此时应显示配置引导而不是弹错误框 ——
      // 弹窗既吓人又挡住了用户唯一能自救的入口(填 API Key)。
      setIsCharacterReady(false);
      try {
          const st = await axios.get(`${API_BASE_URL}/api/config/llm_status`);
          if (st.data?.configured === false) {
              setNeedsLLMSetup(true);   // 渲染配置引导
              return false;
          }
      } catch {
          // 状态也查不到:后端可能仍在启动,静默重试(轮询会再次触发)
      }
      return false;
    }
    return true; 
  };

  useEffect(() => {
    // Initial check
    checkCharacterStatus();
    
    // Poll if not ready
    const timer = setInterval(async () => {
        const ready = await checkCharacterStatus();
        if (ready) {
             // Keep polling? Maybe less frequently.
             // For now, let's keep checking to detect status changes (e.g. evolving)
        }
    }, 3000); 

    return () => clearInterval(timer);
  }, []);
  
  const startTimeRef = useRef<number>(Date.now());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true); // Track if user is at bottom

  // Scroll handler
  const onScroll = () => {
    if (scrollContainerRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
        // Check if close to bottom (within 50px)
        const isBottom = scrollHeight - scrollTop - clientHeight < 50;
        isAtBottomRef.current = isBottom;
        
        if (isBottom) {
            setShowNewMessageTip(false);
        }
    }
  };

  // Auto scroll to bottom
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        // Force reset states after scroll
        setShowNewMessageTip(false);
        isAtBottomRef.current = true;
    }
  };

  // Smart Scroll Effect
  useEffect(() => {
    const lastMessage = messages[messages.length - 1];
    
    // 1. If it's the user's message, always scroll to bottom
    if (lastMessage?.role === 'user') {
        setTimeout(scrollToBottom, 100);
        return;
    }

    // 2. If user is already at bottom, scroll to show new content
    if (isAtBottomRef.current) {
        setTimeout(scrollToBottom, 100);
    } else {
        // 3. If user is scrolling up and new content arrives, show tip
        // But only if we have messages (not empty state)
        if (messages.length > 0) {
            setShowNewMessageTip(true);
        }
    }
  }, [messages]);

  const resetSessionStats = () => {
    startTimeRef.current = Date.now();
    setInteractionCount(0);
  };

  const handleSend = async () => {
    if (!input.trim()) return;
    
    // Strict Block
    if (!isCharacterReady) {
         message.error("系统未就绪，无法发送消息");
         return;
    }

    // Double check (redundant but safe)
    try {
        const res = await axios.get(`${API_BASE_URL}/api/config/common`);
        if (res.data && res.data.has_character_card === false) {
             // Should trigger the modal via polling, but here we just block
             message.error("角色卡正在生成中，请稍候...");
             return;
        }
    } catch (e) {
        // Network error, block
        message.error("无法连接到服务器");
        return;
    }
    
    const content = input;
    setInput(''); // Clear input immediately
    
    await sendMessage(content);
    setInteractionCount(prev => prev + 1);
  };

  const handleRetry = async (content: string) => {
      // Retry by sending as a new message
      await sendMessage(content);
  };

  const handleNewSessionBoundary = async () => {
      const nextSessionId = await startNewSession({ endCurrent: true });
      if (!nextSessionId) {
          return;
      }

      resetSessionStats();
      message.success("已切换到新会话");
  };

  const handleDownloadMarkdown = () => {
    const validMessages = messages.filter(msg => msg.role === 'user' || msg.role === 'ai');

    if (validMessages.length === 0) {
      message.warning('暂无聊天记录可下载');
      return;
    }

    let mdContent = `# Chat Session - ${new Date().toLocaleString()}\n\n`;
    validMessages.forEach(msg => {
      const roleName = msg.role === 'ai' ? aiName : 'User';
      mdContent += `### **${roleName}:**\n${msg.content}\n`;
      if (msg.action) {
          mdContent += `> *Action: ${msg.action}*\n`;
      }
      mdContent += `\n`;
      mdContent += `---\n\n`;
    });

    const blob = new Blob([mdContent], { type: 'text/markdown;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `chat_session_${new Date().toISOString().slice(0,10)}.md`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleEndSession = async () => {
      const duration = (Date.now() - startTimeRef.current) / 1000;
      onSessionEnd(duration, interactionCount);
      
      try {
        await axios.post(`${API_BASE_URL}/api/session/end`, {
            session_id: sessionId || "unknown",
            duration_seconds: duration,
            interaction_count: interactionCount
        });
        const nextSessionId = await startNewSession({ endCurrent: false });
        resetSessionStats();

        if (nextSessionId) {
            message.success("会话已结束，已进入新会话");
        } else {
            message.success("会话已结束");
        }
        
      } catch (e) {
          message.error("同步会话结束状态失败");
      }
  };

  const handleBackgroundUpload = async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);

      try {
          const res = await axios.post(`${API_BASE_URL}/api/upload/background`, formData, {
              headers: { 'Content-Type': 'multipart/form-data' }
          });
          const bgPath = res.data.url;
          
          // Update backend config
          const commonRes = await axios.get(`${API_BASE_URL}/api/config/common`);
          const newSettings = { ...commonRes.data, background_image_path: bgPath };
          await axios.post(`${API_BASE_URL}/api/config/common`, newSettings);

          setBackgroundImage(bgPath);
          setBackgroundImageVersion(Date.now());
          await checkCharacterStatus();
          
          message.success('背景图片已更新');
      } catch (error) {
          message.error('背景图片上传失败');
      }
      return false;
  };

  const menuItems: MenuProps['items'] = [
      {
        key: 'bg-upload',
        label: (
            <Upload 
                showUploadList={false} 
                beforeUpload={handleBackgroundUpload}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
                    <PictureOutlined /> 更换背景
                </div>
            </Upload>
        ),
      },
      {
          key: 'new-session',
          label: '新建会话',
          icon: <SendOutlined />,
          onClick: handleNewSessionBoundary,
      },
      {
          key: 'download',
          label: '下载记录',
          icon: <DownloadOutlined />,
          onClick: handleDownloadMarkdown,
      },
      {
          key: 'end',
          label: '结束会话',
          icon: <PoweroffOutlined />,
          danger: true,
          onClick: handleEndSession,
      }
  ];

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%', 
      background: backgroundImage ? `url(${buildAssetUrl(backgroundImage, backgroundImageVersion)}) center/cover no-repeat` : '#f5f5f5', 
      position: 'relative' 
    }}>
      {/* Overlay for background readability if needed */}
      {backgroundImage && (
          <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(255, 255, 255, 0.6)', 
              backdropFilter: 'blur(5px)',
              zIndex: 0
          }} />
      )}
      
      {/* Full Screen Blocking Overlay for Character Generation */}
      {!isCharacterReady && (
        <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(255, 255, 255, 0.85)',
            zIndex: 2000,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            backdropFilter: 'blur(4px)'
        }}>
            {needsLLMSetup ? (
                // 尚未配置模型:直接在此完成首次配置。不要显示加载动画 ——
                // 角色卡生成依赖 API Key,若只转圈,用户既等不到结果也无法去填密钥。
                <div style={{ width: '100%', maxWidth: 600, padding: 16 }}>
                    <LLMSetupGuide
                        onConfigured={() => {
                            setNeedsLLMSetup(false);
                            // 配置完成后立刻复查:后端会重新生成角色卡
                            checkCharacterStatus();
                        }}
                    />
                </div>
            ) : (
                <>
                    <Spin size="large" />
                    <div style={{ marginTop: 10, color: '#1890ff' }}>正在构建数字灵魂...</div>
                    <div style={{ marginTop: 20, textAlign: 'center' }}>
                        <Typography.Title level={4} style={{ margin: 0 }}>角色卡生成中</Typography.Title>
                        <Typography.Text type="secondary">
                            Daisy 正在根据您的设定重组核心记忆，请稍候...
                        </Typography.Text>
                    </div>
                </>
            )}
        </div>
      )}

      {/* Header / Status Bar (Optional, can be added if needed) */}
      <div style={{ 
        padding: '16px 24px', 
        borderBottom: '1px solid rgba(0,0,0,0.06)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'rgba(255, 255, 255, 0.8)',
        backdropFilter: 'blur(10px)',
        zIndex: 1,
        position: 'relative'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ position: 'relative' }}>
            <Avatar 
                size={44} 
                icon={<RobotOutlined />} 
                src={buildAssetUrl(avatarImage, 0)}
                style={{ backgroundColor: '#1890ff' }} 
            />
            <span style={{
              position: 'absolute',
              bottom: 0,
              right: 0,
              width: 10,
              height: 10,
              borderRadius: '50%',
              backgroundColor: isConnected && isCharacterReady ? '#52c41a' : '#ff4d4f',
              border: '2px solid #fff'
            }} />
          </div>
          <div>
            <Typography.Title level={5} style={{ margin: 0, fontSize: '16px' }}>
              {aiName}
            </Typography.Title>
            <Typography.Text type="secondary" style={{ fontSize: '12px' }}>
              {isConnected ? (isCharacterReady ? (characterStatusText || 'Online') : 'Initializing...') : 'Disconnected'}
            </Typography.Text>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
             <Dropdown menu={{ items: menuItems }} placement="bottomRight" trigger={['click']}>
                 <Button type="text" icon={<EllipsisOutlined style={{ fontSize: '20px' }} />} />
             </Dropdown>
        </div>
      </div>

      <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        <div 
            ref={scrollContainerRef}
            onScroll={onScroll}
            style={{ height: '100%', overflowY: 'auto', padding: '20px' }}
        >
            {messages.map((item) => (
            <div key={item.id} style={{ 
                display: 'flex', 
                flexDirection: item.role === 'user' ? 'row-reverse' : 'row',
                marginBottom: '20px',
                alignItems: 'flex-start'
            }}>
                {/* Avatar */}
                <Avatar 
                size={40} 
                shape="square"
                src={buildAssetUrl(item.role === 'ai' ? avatarImage : userAvatarImage, 0)}
                icon={item.role === 'ai' ? <RobotOutlined /> : <UserOutlined />} 
                style={{ 
                    // 只有在没有自定义头像时才铺底色,否则底色会从图片边缘透出来
                    backgroundColor: item.role === 'ai'
                        ? (avatarImage ? 'transparent' : '#fff')
                        : (userAvatarImage ? 'transparent' : '#87d068'),
                    color: item.role === 'ai' ? '#000' : '#fff',
                    marginLeft: item.role === 'user' ? '10px' : '0',
                    marginRight: item.role === 'ai' ? '10px' : '0',
                    borderRadius: '4px'
                }} 
                />
                
                {/* Message Bubble */}
                <div style={{ 
                maxWidth: '70%',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
                }}>
                {/* Status Icons */}
                {/* 发送失败的重试入口。原先是个光秃秃的红色感叹号,点一下就静默重发 ——
                    没有说明、没有确认,极易误触,而每次误触都要重跑一整轮对话(烧 token)。
                    加提示文案 + 二次确认。 */}
                {item.role === 'user' && item.status === 'error' && (
                    <Tooltip title="发送失败,点击重新发送这条消息">
                    <ExclamationCircleFilled
                        style={{ color: '#ff4d4f', fontSize: '18px', cursor: 'pointer' }}
                        onClick={() => Modal.confirm({
                            title: '重新发送这条消息?',
                            content: item.content.length > 60
                                ? item.content.slice(0, 60) + '…'
                                : item.content,
                            okText: '重新发送',
                            cancelText: '取消',
                            onOk: () => handleRetry(item.content),
                        })}
                    />
                    </Tooltip>
                )}
                {(item.role === 'user' && item.status === 'sending') && (
                    <LoadingOutlined style={{ color: '#ccc', fontSize: '16px' }} />
                )}

                <div style={{ 
                    background: item.role === 'user' ? '#95ec69' : '#fff', 
                    padding: '10px 14px', 
                    borderRadius: '4px',
                    color: '#000',
                    fontSize: '14px',
                    lineHeight: '1.6',
                    position: 'relative',
                    wordBreak: 'break-word'
                }}>
                    {/* Arrow CSS */}
                    <div style={{
                        position: 'absolute',
                        top: '14px',
                        [item.role === 'user' ? 'right' : 'left']: '-6px',
                        width: '0',
                        height: '0',
                        borderTop: '6px solid transparent',
                        borderBottom: '6px solid transparent',
                        [item.role === 'user' ? 'borderLeft' : 'borderRight']: `6px solid ${item.role === 'user' ? '#95ec69' : '#fff'}`
                    }} />

                    {item.content && <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>}
                    
                    {/* Collapsible Action Description */}
                    {item.action && (
                        <Collapse 
                        ghost 
                        size="small" 
                        style={item.content ? { marginTop: '8px', borderTop: '1px solid #eee' } : {}}
                        items={[
                        {
                            key: '1',
                            label: <span style={{ fontSize: '12px', color: '#888' }}><EyeOutlined /> 查看环境/动作描述</span>,
                            children: (
                            <div style={{ 
                                fontSize: '12px', 
                                color: '#666', 
                                background: '#f9f9f9', 
                                padding: '8px', 
                                borderRadius: '4px',
                                fontStyle: 'italic'
                            }}>
                                {item.action}
                            </div>
                            )
                        }
                        ]}
                    />
                    )}
                </div>
                </div>
            </div>
            ))}
            <div ref={messagesEndRef} />
        </div>

        {showNewMessageTip && (
            <div 
                onClick={scrollToBottom}
                style={{
                    position: 'absolute',
                    bottom: '20px',
                    right: '20px',
                    background: '#1890ff',
                    color: '#fff',
                    padding: '8px 16px',
                    borderRadius: '20px',
                    cursor: 'pointer',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
                    zIndex: 10,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '12px',
                    transition: 'all 0.3s'
                }}
            >
                <DownOutlined /> 有新消息
            </div>
        )}
      </div>
      
      <div style={{ 
        borderTop: '1px solid #e5e5e5', 
        background: '#fff', 
        padding: '20px',
        display: 'flex', 
        flexDirection: 'column', 
        gap: '10px' 
      }}>
        <div style={{ display: 'flex', gap: '10px' }}>
            <TextArea 
            value={input} 
            onChange={e => setInput(e.target.value)} 
            onPressEnter={(e) => { 
                if(!e.shiftKey) { 
                    e.preventDefault(); 
                    // Use setTimeout to avoid conflict with TextArea autoSize or event handling
                    setTimeout(() => {
                        handleSend();
                    }, 0);
                } 
            }}
            placeholder="输入消息... (Shift+Enter 换行)" 
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={loading} // Optional: disable while sending? User said "随便发送", so maybe don't disable. But loading state is usually good.
            />
            <Button 
                type="primary" 
                icon={loading ? <LoadingOutlined /> : <SendOutlined />} 
                onClick={handleSend}
                disabled={loading || !input.trim()}
            />
             {/* 必须显式指定 click:antd Dropdown 默认 trigger 是 hover,
                 用户点了没反应会以为"更换背景"这个功能不存在(实测踩过)。
                 与顶部那个 Dropdown 保持一致。 */}
             <Dropdown menu={{ items: menuItems }} placement="topRight" trigger={['click']}>
                <Button icon={<EllipsisOutlined />} />
            </Dropdown>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;
