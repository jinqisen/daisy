import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { Card, Typography, Collapse, Tag } from 'antd';
import { DatabaseOutlined, RobotOutlined, ScanOutlined, TeamOutlined, EditOutlined, SaveOutlined, HeartOutlined, HistoryOutlined, UserOutlined, BulbOutlined } from '@ant-design/icons';

const { Text } = Typography;

// Helper to format data
const formatData = (data: any) => {
    if (!data) return <span style={{ color: '#ccc' }}>No Data</span>;
    
    // Check if data contains internal_tasks (Generic handling)
    if (data.internal_tasks) {
         const tasks = data.internal_tasks;
         return (
            <div>
                {/* Render other fields first */}
                {Object.entries(data).filter(([k]) => k !== 'internal_tasks').map(([key, value]) => (
                    <div key={key} style={{ marginBottom: '6px', borderBottom: '1px dashed #eee', paddingBottom: '2px' }}>
                        <div style={{ fontWeight: 'bold', color: '#1890ff', marginBottom: '2px' }}>{key}:</div>
                        <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#333', paddingLeft: '8px' }}>
                            {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                        </div>
                    </div>
                ))}
                
                <div style={{ marginTop: 10, marginBottom: 5, fontWeight: 'bold', color: '#722ed1' }}>Internal Tasks:</div>
                <div style={{ paddingLeft: 10 }}>
                    {formatData(tasks)}
                </div>
            </div>
         );
    }

    if (typeof data === 'object' && data !== null) {
        if (Object.keys(data).length === 0) return <span style={{ color: '#ccc' }}>Empty</span>;

        return (
            <div style={{ maxHeight: '200px', overflowY: 'auto', fontSize: '11px', fontFamily: 'monospace' }}>
                {Object.entries(data).map(([key, value]) => (
                    <div key={key} style={{ marginBottom: '6px', borderBottom: '1px dashed #eee', paddingBottom: '2px' }}>
                        <div style={{ fontWeight: 'bold', color: '#1890ff', marginBottom: '2px' }}>{key}:</div>
                        <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#333', paddingLeft: '8px' }}>
                            {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                        </div>
                    </div>
                ))}
            </div>
        );
    }
    return String(data);
};

const TraceNode = memo(({ data, isConnectable }: NodeProps) => {
    const { label, type, trace, is_llm } = data;

    let icon = <RobotOutlined />;
    if (label.toLowerCase().includes("analyze")) icon = <ScanOutlined />;
    if (label.toLowerCase().includes("retrieve")) icon = <DatabaseOutlined />;
    if (label.toLowerCase().includes("consult")) icon = <TeamOutlined />;
    if (label.toLowerCase().includes("generate")) icon = <EditOutlined />;
    if (label.toLowerCase().includes("save")) icon = <SaveOutlined />;
    if (label.toLowerCase().includes("love")) icon = <HeartOutlined />;
    if (label.toLowerCase().includes("summarize") || label.toLowerCase().includes("history")) icon = <HistoryOutlined />;
    if (label.toLowerCase().includes("portrait") || label.toLowerCase().includes("ensure")) icon = <UserOutlined />;
    if (label.toLowerCase().includes("communication") || label.toLowerCase().includes("style")) icon = <BulbOutlined />;

    // Determine border color based on execution status
    // If trace exists, it ran.
    const borderColor = trace ? '#52c41a' : (is_llm ? '#b37feb' : '#d9d9d9');
    const bgColor = trace ? '#f6ffed' : '#ffffff';
    const headerColor = is_llm && !trace ? '#f9f0ff' : bgColor; // Slight purple tint for unexecuted LLM nodes

    return (
        <div className="trace-node" style={{ minWidth: '250px' }}>
            <Handle
                type="target"
                position={Position.Left}
                isConnectable={isConnectable}
                style={{ background: '#555' }}
            />
            <Card 
                size="small" 
                title={
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span>{icon} {label}</span>
                        {is_llm && <Tag color="purple" style={{ marginLeft: 8, fontSize: 10, marginRight: 0 }}>LLM</Tag>}
                    </div>
                }
                styles={{ 
                    header: { background: headerColor, borderBottom: `1px solid ${borderColor}` },
                    body: { padding: '5px' }
                }}
                style={{ border: `1px solid ${borderColor}`, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}
            >
                {trace ? (
                    <Collapse 
                        ghost 
                        size="small" 
                        items={[
                            {
                                key: 'input',
                                label: <Text type="secondary" style={{ fontSize: '11px' }}>Input</Text>,
                                children: formatData(trace.input)
                            },
                            {
                                key: 'output',
                                label: <Text type="secondary" style={{ fontSize: '11px' }}>Output</Text>,
                                children: (
                                    <>
                                        {trace.output && trace.output.internal_tasks && (
                                            <div style={{ marginBottom: '8px', border: '1px dashed #d9d9d9', borderRadius: '4px', padding: '4px' }}>
                                                <Text strong style={{ fontSize: '11px', color: '#1890ff' }}>Internal Tasks (Parallel):</Text>
                                                {formatData(trace.output.internal_tasks)}
                                            </div>
                                        )}
                                        {formatData(trace.output)}
                                    </>
                                )
                            }
                        ]}
                    />
                ) : (
                     <div style={{ padding: '10px', color: '#ccc', textAlign: 'center', fontSize: '12px' }}>
                         Waiting for execution...
                     </div>
                )}
            </Card>
            <Handle
                type="source"
                position={Position.Right}
                isConnectable={isConnectable}
                style={{ background: '#555' }}
            />
        </div>
    );
});

export default TraceNode;
