import React, { useEffect, useState, useCallback } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Node,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import dagre from 'dagre';
import axios from 'axios';
import { Spin, Alert, List, Card, Typography, Layout, message, Drawer, Descriptions, Divider, Collapse } from 'antd';
import { MessageOutlined, ClockCircleOutlined, UserOutlined, DatabaseOutlined, RobotOutlined, ScanOutlined, TeamOutlined, EditOutlined, SaveOutlined, HeartOutlined, BulbOutlined } from '@ant-design/icons';
import { API_BASE_URL } from '../config';

import TraceNode from './TraceNode';

const { Sider, Content } = Layout;
const { Text, Title } = Typography;

const nodeTypes = {
  traceNode: TraceNode,
};

// Layout function using dagre
const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'LR') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 300; // Increased for TraceNode
  const nodeHeight = 150; // Increased for TraceNode

  // Adjusted for better parallel node visualization
  dagreGraph.setGraph({ rankdir: direction, ranksep: 150, nodesep: 80 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    node.targetPosition = direction === 'LR' ? Position.Left : Position.Top;
    node.sourcePosition = direction === 'LR' ? Position.Right : Position.Bottom;

    // We are shifting the dagre node position (anchor=center center) to the top left
    // so it matches the React Flow node anchor point (top left).
    node.position = {
      x: nodeWithPosition.x - nodeWidth / 2,
      y: nodeWithPosition.y - nodeHeight / 2,
    };

    return node;
  });

  return { nodes, edges };
};

interface WorkflowVisualizerProps {
    traceData?: any; // Kept for backward compatibility or initial state
}

const WorkflowVisualizer: React.FC<WorkflowVisualizerProps> = ({ traceData: initialTraceData }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // New state for history list
  const [historyTurns, setHistoryTurns] = useState<any[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<any>(initialTraceData || null);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  
  // Drawer state
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    setSelectedNode(node);
    setDrawerVisible(true);
  }, []);

  const renderNodeDetails = () => {
      if (!selectedNode) return null;
      const { data } = selectedNode;
      const { label, trace } = data;

      // Icon logic similar to TraceNode
      let icon = <RobotOutlined />;
      if (label && typeof label === 'string') {
          if (label.toLowerCase().includes("analyze")) icon = <ScanOutlined />;
          if (label.toLowerCase().includes("retrieve")) icon = <DatabaseOutlined />;
          if (label.toLowerCase().includes("consult")) icon = <TeamOutlined />;
          if (label.toLowerCase().includes("generate")) icon = <EditOutlined />;
          if (label.toLowerCase().includes("save")) icon = <SaveOutlined />;
          if (label.toLowerCase().includes("love")) icon = <HeartOutlined />;
      }

      // Reuse logic from TraceNode for data formatting
      // We can duplicate the helper function here or export it. 
      const formatData = (data: any) => {
          if (!data) return <span style={{ color: '#ccc' }}>No Data</span>;
          
          if (typeof data === 'object' && data !== null) {
              if (Object.keys(data).length === 0) return <span style={{ color: '#ccc' }}>Empty</span>;

              return (
                  <div style={{ maxHeight: '400px', overflowY: 'auto', fontSize: '12px', fontFamily: 'monospace' }}>
                      {Object.entries(data).map(([key, value]) => (
                          <div key={key} style={{ marginBottom: '8px', borderBottom: '1px dashed #eee', paddingBottom: '4px' }}>
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

      return (
          <div style={{ paddingBottom: '20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '20px' }}>
                  <div style={{ fontSize: '24px', marginRight: '10px', color: '#1890ff' }}>{icon}</div>
                  <Title level={4} style={{ margin: 0 }}>{label}</Title>
              </div>
              
              {!trace ? (
                  <Alert message="该节点在此次对话中未执行" type="info" showIcon />
              ) : (
                  <>
                      <Descriptions title="基本信息" column={1} bordered size="small">
                          <Descriptions.Item label="状态">
                              <span style={{ color: '#52c41a', fontWeight: 'bold' }}>已执行</span>
                          </Descriptions.Item>
                          {trace.timestamp && (
                              <Descriptions.Item label="执行时间">{trace.timestamp}</Descriptions.Item>
                          )}
                      </Descriptions>

                      <Divider orientation="left">输入数据 (Input)</Divider>
                      <div style={{ 
                          background: '#f5f5f5', 
                          padding: '10px', 
                          borderRadius: '4px', 
                          overflowX: 'hidden', 
                          overflowY: 'auto'
                      }}>
                          {formatData(trace.input)}
                      </div>

                      <Divider orientation="left">输出数据 (Output)</Divider>
                      <div style={{ 
                          background: '#f5f5f5', 
                          padding: '10px', 
                          borderRadius: '4px', 
                          overflowX: 'hidden', 
                          overflowY: 'auto'
                      }}>
                          {trace.output && trace.output.internal_tasks && (
                              <div style={{ marginBottom: '16px', border: '1px dashed #1890ff', borderRadius: '4px', padding: '8px', background: '#e6f7ff' }}>
                                  <Text strong style={{ fontSize: '14px', color: '#1890ff', display: 'block', marginBottom: '8px' }}>Internal Tasks (Parallel Execution):</Text>
                                  {formatData(trace.output.internal_tasks)}
                              </div>
                          )}
                          {formatData(trace.output)}
                      </div>
                  </>
              )}
          </div>
      );
  };

  const fetchHistory = useCallback(async () => {
      try {
          const res = await axios.get(`${API_BASE_URL}/api/chat/history`);
          const rawHistory = res.data;
          const turns: any[] = [];
          
          // Process into turns (User -> AI)
          for (let i = 0; i < rawHistory.length; i++) {
              if (rawHistory[i].role === 'user') {
                  const userMsg = rawHistory[i];
                  // Look ahead for AI response
                  let aiMsg = null;
                  if (i + 1 < rawHistory.length && rawHistory[i+1].role === 'ai') {
                      aiMsg = rawHistory[i+1];
                  }
                  
                  turns.push({
                      id: userMsg.id, // Use user message ID as turn ID
                      userMessage: userMsg,
                      aiMessage: aiMsg,
                      timestamp: userMsg.timestamp
                  });
              }
          }
          
          // Sort by timestamp descending (newest first)
          turns.sort((a, b) => b.timestamp - a.timestamp);
          
          setHistoryTurns(turns);
      } catch (e) {
          console.error("Failed to fetch history for workflow", e);
      }
  }, []);

  // Update selectedTrace if prop changes (e.g. from real-time chat)
  useEffect(() => {
      if (initialTraceData) {
          setSelectedTrace(initialTraceData);
          fetchHistory(); // Refresh history list when new trace arrives
      }
  }, [initialTraceData, fetchHistory]);

  useEffect(() => {
      fetchHistory();
  }, [fetchHistory]);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_BASE_URL}/api/workflow`);
      const { nodes: apiNodes, edges: apiEdges } = response.data;

      // Format edges with markers
      let formattedEdges = apiEdges.map((edge: any) => ({
        ...edge,
        type: 'smoothstep', // Use string directly or import ConnectionLineType
        markerEnd: {
          type: MarkerType.ArrowClosed,
        },
        style: { stroke: '#b1b1b7' },
        animated: true,
      }));
      
      // Direct mapping of nodes (No artificial sub-task expansion)
      const formattedNodes = apiNodes.map((node: any) => ({
          ...node,
          type: 'traceNode',
          data: {
              label: node.data.label,
              type: node.type,
              is_llm: node.data.is_llm,
              icon: node.data.icon,
              trace: selectedTrace ? selectedTrace[node.id] : null
          },
      }));

      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        formattedNodes,
        formattedEdges
      );

      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch workflow:", err);
      setError("Failed to load workflow data. Please ensure the backend is running.");
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges, selectedTrace]); 

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Force update nodes when selectedTrace changes (without re-fetching layout if not needed)
  useEffect(() => {
      setNodes((nds) => 
        nds.map((node) => {
            const traceData = selectedTrace ? selectedTrace[node.id] : null;

            return {
              ...node,
              data: {
                ...node.data,
                trace: traceData
              }
            };
        })
      );
  }, [selectedTrace, setNodes]);

  const handleTurnSelect = (turn: any) => {
      console.log("Selected turn:", turn); // Debug log
      setSelectedTurnId(turn.id);
      
      const aiMsg = turn.aiMessage;
      if (aiMsg && aiMsg.state_snapshot && aiMsg.state_snapshot.workflow_trace) {
          console.log("Trace found in AI message:", aiMsg.state_snapshot.workflow_trace); // Debug log
          setSelectedTrace(aiMsg.state_snapshot.workflow_trace);
          message.success("已加载该消息的工作流数据");
      } else {
          console.log("No trace found for this turn."); // Debug log
          setSelectedTrace(null);
          message.warning("该历史消息无工作流记录");
      }
  };

  if (loading && !nodes.length) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Spin size="large" />
        <div style={{ marginTop: 16 }}>Loading workflow...</div>
      </div>
    );
  }
  
  if (error) return <Alert message="Error" description={error} type="error" showIcon style={{ margin: '20px' }} />;

  return (
    <Layout style={{ height: '100%', background: 'transparent' }}>
        <Sider width={300} theme="light" style={{ borderRight: '1px solid #eee', overflowY: 'auto', background: '#fff' }}>
            <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0' }}>
                <Title level={5} style={{ margin: 0 }}>历史对话追踪</Title>
                <Text type="secondary" style={{ fontSize: '12px' }}>点击查看工作流执行详情</Text>
            </div>
            <List
                itemLayout="vertical"
                dataSource={historyTurns}
                renderItem={(turn, index) => {
                    const isSelected = turn.id === selectedTurnId;
                    return (
                        <List.Item 
                            key={turn.id || index}
                            onClick={() => handleTurnSelect(turn)}
                            style={{ 
                                padding: '12px 16px', 
                                cursor: 'pointer',
                                background: isSelected ? '#e6f7ff' : 'transparent',
                                borderLeft: isSelected ? '3px solid #1890ff' : '3px solid transparent',
                                transition: 'all 0.3s',
                                width: '100%',
                                display: 'block' // Ensure it takes full width for click area
                            }}
                        >
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', width: '100%' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#999' }}>
                                    <span><ClockCircleOutlined /> {new Date(turn.timestamp * 1000).toLocaleTimeString()}</span>
                                    <span>#{historyTurns.length - index}</span>
                                </div>
                                <div style={{ fontWeight: 'bold', color: '#333', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    <UserOutlined /> 用户消息
                                </div>
                                <div style={{ fontSize: '12px', color: '#666', maxHeight: '40px', overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                                    {turn.userMessage.content}
                                </div>
                            </div>
                        </List.Item>
                    );
                }}
            />
        </Sider>
        <Content style={{ height: '100%', backgroundColor: '#f0f2f5' }}>
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                nodeTypes={nodeTypes} // Register custom types
                fitView
                style={{ backgroundColor: '#f0f2f5' }}
            >
                <Controls />
                <Background color="#ccc" gap={20} />
            </ReactFlow>
            
            <Drawer
                title="节点详情"
                placement="right"
                onClose={() => setDrawerVisible(false)}
                open={drawerVisible}
                width={500}
                styles={{ body: { paddingBottom: 80 } }}
            >
                {renderNodeDetails()}
            </Drawer>
        </Content>
    </Layout>
  );
};

export default WorkflowVisualizer;
