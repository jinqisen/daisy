import React, { useEffect, useState } from 'react';
import { Card, Typography, Descriptions, Tag, Divider, Collapse } from 'antd';
import { HeartOutlined, BulbOutlined, CodeOutlined, MessageOutlined } from '@ant-design/icons';
import axios from 'axios';
import { API_BASE_URL } from '../config';

const { Text, Paragraph } = Typography;

interface CommunicationAnalysisCardProps {
  logs: any[];
  latestUserMessageId?: number | null;
}

const styleTranslations: Record<string, string> = {
  Eros: "热情/直接 (Eros)",
  Ludus: "幽默/轻松 (Ludus)",
  Storge: "友伴/支持 (Storge)",
  Pragma: "理性/务实 (Pragma)",
  Mania: "激烈/表达 (Mania)",
  Agape: "奉献/安抚 (Agape)"
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

const CommunicationAnalysisCard: React.FC<CommunicationAnalysisCardProps> = ({ logs, latestUserMessageId }) => {
  const [fetchedData, setFetchedData] = useState<any>(null);

  useEffect(() => {
    if (latestUserMessageId) {
      console.log("Fetching analysis for message ID:", latestUserMessageId);
      axios.get(`${API_BASE_URL}/api/chat/message/${latestUserMessageId}/analysis`)
        .then(res => {
          if (res.data && res.data.status !== "no_data") {
            console.log("Fetched analysis data:", res.data);
            // Ensure the structure matches what we expect (ui_card_data)
            // The API returns the ui_card_data object directly
            setFetchedData(res.data);
          }
        })
        .catch(err => console.error("Failed to fetch analysis", err));
    }
  }, [latestUserMessageId]);

  // Find the latest Communication Analysis log
  // Search in reverse order to get the most recent one
  // Support both new title and old title for compatibility
  // Also check for trace data if logs are empty (fallback)
  
  // Priority: Fetched Data -> Logs
  let analysisLog = fetchedData;

  if (!analysisLog) {
      analysisLog = logs.slice().reverse().find(log => 
        log.title === "Communication Analysis (Psychology Expert)" || 
        log.title === "Love Style Analysis (Psychology Expert)"
      );
  }
  
  // Fallback: Check if logs contain raw trace output from analyze_communication_style
  if (!analysisLog) {
      const traceLog = logs.slice().reverse().find(log => 
          log.node_id === "analyze_communication_style" && log.output_data && log.output_data.ui_card_data
      );
      if (traceLog) {
          analysisLog = traceLog.output_data.ui_card_data;
      }
  }

  // Double Check: Sometimes traceLog is passed directly as a log item
  if (!analysisLog) {
      analysisLog = logs.slice().reverse().find(log => 
          log.content && log.content.best_match && log.content.reasoning
      );
  }

  // Final check: Look for the specific structure in the logs array itself (sometimes logs are just the ui_card_data objects)
  if (!analysisLog) {
      analysisLog = logs.slice().reverse().find(log => 
          log.best_match && log.weights && log.reasoning
      );
  }

  if (!analysisLog) {
    return (
      <Card title="沟通情感分析 (心理学专家)" size="small" style={{ height: '100%' }}>
        <div style={{ padding: '20px', textAlign: 'center', color: '#999' }}>
          暂无研判数据
        </div>
      </Card>
    );
  }

  // Handle different structures of analysisLog
  // Case 1: Wrapped in content (from logs array with title)
  let content = analysisLog.content || analysisLog;
  
  // Case 2: Direct object (from trace or direct fetch)
  if (!content.best_match && analysisLog.best_match) {
      content = analysisLog;
  }
  
  const weights = content.weights || {};
  const sortedWeights = Object.entries(weights)
    .sort(([, a]: any, [, b]: any) => b - a)
    .filter(([, v]: any) => v > 0);

  return (
    <Card 
        title={
            <span>
                <HeartOutlined style={{ color: '#eb2f96', marginRight: 8 }} />
                沟通情感分析 (心理学专家)
            </span>
        } 
        size="small" 
        variant="borderless"
        style={{ height: '100%', overflowY: 'auto' }}
    >
      <Descriptions column={{ xxl: 4, xl: 3, lg: 3, md: 2, sm: 1, xs: 1 }} size="small" bordered>
        <Descriptions.Item label="最佳策略">
          <Tag color="#eb2f96" style={{ fontSize: '14px', padding: '4px 10px' }}>
            {styleTranslations[content.best_match] || content.best_match}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="检测情感">
            {content.top_emotions && content.top_emotions.map(([emo, score]: any) => (
                <Tag key={emo} color="blue">{emotionTranslations[emo] || emo} {(score * 100).toFixed(0)}%</Tag>
            ))}
        </Descriptions.Item>
        <Descriptions.Item label="风格分布">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                {sortedWeights.map(([key, value]: any) => (
                    <Tag key={key} bordered={false} color={key === content.best_match ? "magenta" : "default"}>
                        {styleTranslations[key] || key}: {(value * 100).toFixed(0)}%
                    </Tag>
                ))}
            </div>
        </Descriptions.Item>
      </Descriptions>
      
      <Divider style={{ margin: '12px 0' }} orientation="left">
        <MessageOutlined /> 上下文输入
      </Divider>
      <Paragraph 
        ellipsis={{ tooltip: content.input_context, rows: 2, expandable: true, symbol: '展开' }} 
        style={{ fontSize: '13px', background: '#f0f5ff', padding: '10px', borderRadius: '4px', marginBottom: '0' }}
      >
          {content.input_context}
      </Paragraph>

      <Divider style={{ margin: '12px 0' }} orientation="left">
        <BulbOutlined /> 专家推理 (心理学视角)
      </Divider>
      <Paragraph type="secondary" style={{ fontSize: '13px', background: '#f9f9f9', padding: '10px', borderRadius: '4px' }}>
        {content.reasoning || "无推理内容"}
      </Paragraph>

      <Collapse 
        ghost 
        size="small" 
        items={[
            {
                key: '1',
                label: <span style={{ fontSize: '12px', color: '#888' }}><CodeOutlined /> 查看专家提示词 (Prompt)</span>,
                children: (
                    <pre style={{ 
                        whiteSpace: 'pre-wrap', 
                        wordWrap: 'break-word', 
                        fontSize: '11px', 
                        color: '#666',
                        background: '#f0f0f0',
                        padding: '8px',
                        borderRadius: '4px',
                        maxHeight: '200px',
                        overflowY: 'auto'
                    }}>
                        {content.prompt}
                    </pre>
                )
            }
        ]}
      />
    </Card>
  );
};

export default CommunicationAnalysisCard;