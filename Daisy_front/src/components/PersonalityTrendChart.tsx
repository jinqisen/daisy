import React, { useMemo } from 'react';
import { Card } from 'antd';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';

interface PersonalityTrendChartProps {
  personalityHistory: any[];
}

const personalityTranslations: Record<string, string> = {
  Eros: "热情/直接 (Eros)",
  Ludus: "幽默/轻松 (Ludus)",
  Storge: "友伴/支持 (Storge)",
  Pragma: "理性/务实 (Pragma)",
  Mania: "激烈/表达 (Mania)",
  Agape: "奉献/安抚 (Agape)"
};

const colors: Record<string, string> = {
  Eros: 'magenta',
  Ludus: 'orange',
  Storge: 'green',
  Pragma: 'blue',
  Mania: 'purple',
  Agape: 'cyan'
};

const PersonalityTrendChart: React.FC<PersonalityTrendChartProps> = ({ personalityHistory = [] }) => {
  // Extract all keys that have at least one non-zero value
  const activeKeys = useMemo(() => {
    const keys = new Set<string>();
    personalityHistory.forEach(entry => {
      Object.keys(entry).forEach(key => {
        if (key !== 'index' && typeof entry[key] === 'number') {
          keys.add(key);
        }
      });
    });
    return Array.from(keys).sort();
  }, [personalityHistory]);

  const minWidth = Math.max(100, personalityHistory.length * 60);

  return (
    <Card title="沟通风格趋势 (Communication Styles)" size="small" variant="borderless" style={{ height: '100%' }}>
      <div style={{ height: 300, width: '100%', overflowX: 'auto', overflowY: 'hidden' }}>
        <div style={{ width: `${minWidth}px`, height: '100%', minWidth: '100%' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={personalityHistory}>
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
                  stroke={colors[key] || '#888'} 
                  name={`${personalityTranslations[key] || key}`}
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

export default PersonalityTrendChart;
