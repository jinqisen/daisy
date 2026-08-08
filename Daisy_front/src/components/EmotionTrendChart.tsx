import React, { useMemo } from 'react';
import { Card } from 'antd';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';

interface EmotionTrendChartProps {
  emotionHistory: any[];
}

const emotionTranslations: Record<string, string> = {
  admiration: "钦佩",
  amusement: "娱乐",
  anger: "愤怒",
  annoyance: "恼怒",
  approval: "赞同",
  caring: "关怀",
  confusion: "困惑",
  curiosity: "好奇",
  desire: "渴望",
  disappointment: "失望",
  disapproval: "反对",
  disgust: "厌恶",
  embarrassment: "尴尬",
  excitement: "兴奋",
  fear: "恐惧",
  gratitude: "感激",
  grief: "悲伤",
  joy: "快乐",
  love: "爱",
  nervousness: "紧张",
  optimism: "乐观",
  pride: "骄傲",
  realization: "领悟",
  relief: "解脱",
  remorse: "懊悔",
  sadness: "悲哀",
  surprise: "惊讶",
  neutral: "中性"
};

// Generate distinct colors based on key string to ensure stability
const getColor = (key: string) => {
  const colors = [
    '#ff7300', '#387908', '#ff0000', '#000000', '#ff69b4', '#8884d8',
    '#82ca9d', '#a4de6c', '#d0ed57', '#ffc658', '#8dd1e1', '#83a6ed',
    '#8e44ad', '#e74c3c', '#3498db', '#16a085', '#f1c40f', '#d35400',
    '#2c3e50', '#7f8c8d', '#c0392b', '#bdc3c7', '#2ecc71', '#e67e22'
  ];
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = key.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % colors.length;
  return colors[index];
};

const EmotionTrendChart: React.FC<EmotionTrendChartProps> = ({ emotionHistory = [] }) => {
  // Extract all keys that have at least one non-zero value
  const activeKeys = useMemo(() => {
    const keys = new Set<string>();
    emotionHistory.forEach(entry => {
      Object.keys(entry).forEach(key => {
        if (key !== 'index' && typeof entry[key] === 'number' && entry[key] > 0) {
          keys.add(key);
        }
      });
    });
    return Array.from(keys).sort();
  }, [emotionHistory]);

  const minWidth = Math.max(100, emotionHistory.length * 60);

  return (
    <Card title="用户情绪趋势" size="small" variant="borderless" style={{ height: '100%' }}>
      <div style={{ height: 300, width: '100%', overflowX: 'auto', overflowY: 'hidden' }}>
        <div style={{ width: `${minWidth}px`, height: '100%', minWidth: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={emotionHistory}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="index" />
              <YAxis domain={[0, 1]} />
              <Tooltip 
                formatter={(value: number) => value.toFixed(3)}
              />
              <Legend verticalAlign="top" height={36} />
              {activeKeys.map((key) => (
                <Line 
                  key={key} 
                  type="monotone" 
                  dataKey={key} 
                  stroke={getColor(key)} 
                  name={`${emotionTranslations[key] || key}`}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </Card>
  );
};

export default EmotionTrendChart;
