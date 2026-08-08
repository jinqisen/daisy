import React from 'react';
import { Card, Typography, Tag } from 'antd';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, TooltipProps } from 'recharts';

const { Title } = Typography;

interface ReflexionLog {
  timestamp: string;
  user_input?: string;
  agent_response?: string;
  status?: string;
  metrics: {
    Q_I?: number;
    E_U?: number;
    D_R?: number;
    S_total?: number;
    [key: string]: any;
  };
}

interface AiResponseEvaluationChartProps {
  data: ReflexionLog[];
}

const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${month}-${day} ${hours}:${minutes}`;
};

const CustomTooltip = ({ active, payload, label }: TooltipProps<number, string>) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const isPending = data.status === 'pending';

    return (
      <div style={{ 
        backgroundColor: '#fff', 
        border: '1px solid #ccc', 
        padding: '12px', 
        borderRadius: '6px', 
        maxWidth: '400px', 
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        fontSize: '13px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', borderBottom: '1px solid #f0f0f0', paddingBottom: '4px' }}>
            <span style={{ fontWeight: 'bold' }}>{label}</span>
            {isPending && <Tag color="orange" style={{ marginLeft: '8px', marginRight: 0 }}>计算中...</Tag>}
        </div>
        
        <div style={{ marginBottom: '10px' }}>
            {payload.map((entry: any) => (
                <div key={entry.name} style={{ display: 'flex', alignItems: 'center', marginBottom: '2px' }}>
                    <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: entry.color, marginRight: '6px' }}></span>
                    <span style={{ color: '#666' }}>{entry.name}: </span>
                    <span style={{ marginLeft: 'auto', fontWeight: 'bold' }}>
                        {entry.value !== null && entry.value !== undefined ? entry.value : '-'}
                    </span>
                </div>
            ))}
        </div>

        <div style={{ borderTop: '1px solid #eee', paddingTop: '8px' }}>
             {data.user_input && (
                <div style={{ marginBottom: '8px' }}>
                    <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#888', marginBottom: '2px' }}>用户:</div>
                    <div style={{ color: '#333', lineHeight: '1.4', background: '#f5f5f5', padding: '6px', borderRadius: '4px' }}>
                        {data.user_input.length > 60 ? data.user_input.substring(0, 60) + '...' : data.user_input}
                    </div>
                </div>
            )}
            {data.agent_response && (
                <div>
                    <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#888', marginBottom: '2px' }}>AI:</div>
                    <div style={{ 
                        color: '#333', 
                        lineHeight: '1.4', 
                        background: '#e6f7ff', 
                        padding: '6px', 
                        borderRadius: '4px',
                        maxHeight: '150px', 
                        overflowY: 'auto',
                        whiteSpace: 'pre-wrap'
                    }}>
                        {data.agent_response}
                    </div>
                </div>
            )}
        </div>
      </div>
    );
  }

  return null;
};

const AiResponseEvaluationChart: React.FC<AiResponseEvaluationChartProps> = ({ data }) => {
  // Format data for chart
  const chartData = data.map(item => ({
    time: formatDate(item.timestamp),
    status: item.status,
    // Use null for missing values to break the line (or handle in tooltip)
    // Note: Recharts Line connectNulls={false} by default.
    Q_I: item.metrics?.Q_I !== undefined ? Number(item.metrics.Q_I.toFixed(2)) : null,
    E_U: item.metrics?.E_U !== undefined ? Number(item.metrics.E_U.toFixed(2)) : null,
    D_R: item.metrics?.D_R !== undefined ? Number(item.metrics.D_R.toFixed(2)) : null,
    S_total: item.metrics?.S_total !== undefined ? Number(item.metrics.S_total.toFixed(2)) : null,
    user_input: item.user_input,
    agent_response: item.agent_response
  }));

  return (
    <Card 
      title="AI 回复质量评价趋势 (Reflexion)" 
      variant="borderless"
      style={{ width: '100%', height: '100%' }}
    >
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <LineChart
            data={chartData}
            margin={{
              top: 5,
              right: 30,
              left: 20,
              bottom: 5,
            }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend />
            {/* connectNulls={true} makes the line continuous even if some points are null, 
                but here we might want to show gaps or just last known. 
                Actually, pending data usually has Q_I but no others. 
                Let's use connectNulls={false} to show gaps for pending metrics? 
                Or connectNulls={true} to ignore the pending dip? 
                Given user wants to see "data if available", showing the point is key. 
                Null value won't show a point. 
                For pending, S_total is null. So no orange dot for that timestamp. 
                That's correct representation of "delayed settlement". 
            */}
            <Line type="monotone" dataKey="Q_I" name="交互质量 (Q_I)" stroke="#8884d8" activeDot={{ r: 8 }} connectNulls />
            <Line type="monotone" dataKey="E_U" name="用户情感 (E_U)" stroke="#82ca9d" connectNulls />
            <Line type="monotone" dataKey="D_R" name="关系深度 (D_R)" stroke="#ffc658" connectNulls />
            <Line type="monotone" dataKey="S_total" name="综合评分 (S)" stroke="#ff7300" strokeWidth={2} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ marginTop: 10, fontSize: '12px', color: '#666' }}>
        * Q_I: 交互质量 | E_U: 用户情感 | D_R: 关系深度 | S: 综合评分 (范围 0-1)
      </div>
    </Card>
  );
};

export default AiResponseEvaluationChart;
