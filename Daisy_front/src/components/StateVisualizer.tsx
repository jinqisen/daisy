import React from 'react';
import { Card, Progress, Tag } from 'antd';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, BarChart, Bar, Cell, XAxis, YAxis, Tooltip, LineChart, Line, CartesianGrid, Legend } from 'recharts';

interface StateVisualizerProps {
  emotions: { label: string; score: number }[];
  personality: string;
  weights: Record<string, number>;
  engagementHistory?: { index: number; score: number }[];
  emotionHistory?: any[];
}

const StateVisualizer: React.FC<StateVisualizerProps> = ({ emotions, personality, weights, engagementHistory = [], emotionHistory = [] }) => {
  const colors: Record<string, string> = {
    Eros: 'magenta',
    Ludus: 'orange',
    Storge: 'green',
    Pragma: 'blue',
    Mania: 'purple',
    Agape: 'cyan'
  };

  const labels: Record<string, string> = {
    Eros: "爱欲型",
    Ludus: "游戏型",
    Storge: "友伴型",
    Pragma: "现实型",
    Mania: "狂热型",
    Agape: "奉献型"
  };

  const formatPersonality = (text: string) => {
    let formatted = text;
    // Handle "Mix: " prefix if present
    if (formatted.startsWith("Mix: ")) {
       formatted = formatted.replace("Mix: ", "混合模式: ");
    }
    
    // Replace all personality names
    Object.entries(labels).forEach(([eng, chn]) => {
      formatted = formatted.replace(new RegExp(eng, 'g'), chn);
    });
    
    // If it's a direct match in labels (e.g. just "Eros" but somehow missed), use it.
    // But the replace above should handle it. 
    // Just return the formatted string.
    return formatted;
  };

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

  // Prepare data for Radar Chart (Top Emotions)
  const radarData = emotions.map(e => ({
    subject: emotionTranslations[e.label] || e.label,
    A: e.score * 100,
    fullMark: 100,
  }));

  // Prepare data for Bar Chart (Personality Weights)
  const barData = Object.entries(weights).map(([key, value]) => ({
    name: labels[key] || key,
    value: (value * 100).toFixed(1),
    color: colors[key] || '#82ca9d'
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <Card title="人格权重" size="small" variant="borderless">
         <Tag color={colors[personality] || 'blue'} style={{ marginBottom: 10, width: '100%', textAlign: 'center', fontSize: '16px', padding: '5px', whiteSpace: 'normal', height: 'auto' }}>
            {formatPersonality(personality)}
         </Tag>
         <div style={{ height: 200, width: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 5, right: 5, bottom: 20, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="name" 
                angle={-45} 
                textAnchor="end" 
                height={60} 
                interval={0}
                tick={{ fontSize: 12 }}
              />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="value" name="权重 (%)">
                {barData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </div>
  );
};

export default StateVisualizer;
