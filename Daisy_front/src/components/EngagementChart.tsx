import React from 'react';
import { Card } from 'antd';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, TooltipProps } from 'recharts';

interface EngagementChartProps {
  engagementHistory: { 
      index: number; 
      score: number;
      user_input?: string;
      agent_response?: string;
  }[];
}

const CustomTooltip = ({ active, payload, label }: TooltipProps<number, string>) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div style={{ 
        backgroundColor: '#fff', 
        border: '1px solid #ccc', 
        padding: '12px', 
        borderRadius: '6px', 
        maxWidth: '350px', 
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        fontSize: '13px',
        zIndex: 1000
      }}>
        <div style={{ fontWeight: 'bold', marginBottom: '8px', borderBottom: '1px solid #f0f0f0', paddingBottom: '4px' }}>
          Round {label}
        </div>
        <div style={{ marginBottom: '10px' }}>
             <span style={{ color: '#8884d8', fontWeight: 'bold' }}>投入度: {data.score}</span>
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

const EngagementChart: React.FC<EngagementChartProps> = ({ engagementHistory = [] }) => {
  // Calculate dynamic Y-axis max
  const maxScore = Math.max(...engagementHistory.map(h => h.score), 0);
  // Round up to nearest 10 (e.g., 7.8 -> 10, 19.6 -> 20)
  const yAxisMax = Math.ceil(maxScore / 10) * 10;
  // Ensure minimum is at least 10 if maxScore is 0
  const finalMax = yAxisMax === 0 ? 10 : yAxisMax;

  return (
    <Card title="投入指数 (Engagement Score)" size="small" variant="borderless" style={{ height: '100%' }}>
      <div style={{ height: 200, width: '100%' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={engagementHistory}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="index" />
            <YAxis domain={[0, finalMax]} />
            <Tooltip content={<CustomTooltip />} />
            <Line type="monotone" dataKey="score" stroke="#8884d8" name="投入度" isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};

export default EngagementChart;
