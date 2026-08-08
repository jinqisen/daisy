import React, { useEffect, useState } from 'react';
import { Typography, theme } from 'antd';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import StateVisualizer from './StateVisualizer';
import CommunicationAnalysisCard from './CommunicationAnalysisCard';
import PersonalityTrendChart from './PersonalityTrendChart';
import EmotionTrendChart from './EmotionTrendChart';
import EngagementChart from './EngagementChart';
import AiResponseEvaluationChart from './AiResponseEvaluationChart';

const { Title } = Typography;

interface AnalysisDashboardProps {
  visualState: {
    emotions: any[];
    personality: string;
    weights: any;
    engagementHistory: any[];
    emotionHistory: any[];
    personalityHistory: any[];
  };
  logs: any[];
  latestUserMessageId: number | null;
  isSuperUser: boolean;
}

const AnalysisDashboard: React.FC<AnalysisDashboardProps> = ({
  visualState,
  logs,
  latestUserMessageId,
  isSuperUser
}) => {
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const [reflexionData, setReflexionData] = useState<any[]>([]);

  // 跨会话的趋势数据,由本面板**自己**拉取。
  //
  // 踩过的坑:三张趋势图原先复用聊天界面的 visualState,而后者的历史加载
  // 带 session_id 过滤(见 useChat.loadHistory)——「新建会话」后当前会话 0 条快照,
  // 面板瞬间清零。实测:不带过滤返回 12 条快照,带新会话 id 返回 0 条。
  //
  // 分析面板看的是**长期演化**,本就不该被会话边界切断。数据范围不同,
  // 就该有自己的数据源,而不是搭在别人的加载流程上。
  const [trend, setTrend] = useState<{
    engagementHistory: any[]; emotionHistory: any[]; personalityHistory: any[];
  }>({ engagementHistory: [], emotionHistory: [], personalityHistory: [] });

  useEffect(() => {
    axios.get(`${API_BASE_URL}/api/chat/history`, { params: { mode: 'count', limit: 200 } })
      .then(res => {
        const raw = res.data;
        const items: any[] = Array.isArray(raw) ? raw : (raw?.items || raw?.data || []);
        const engagementHistory: any[] = [];
        const emotionHistory: any[] = [];
        const personalityHistory: any[] = [];
        let index = 1;
        items.forEach(item => {
          if (item.role !== 'ai' || !item.state_snapshot) return;
          const s = item.state_snapshot;
          let used = false;
          if (s.engagement_score !== undefined) {
            engagementHistory.push({
              index, score: s.engagement_score,
              user_input: item.user_input, agent_response: item.content,
            });
            used = true;
          }
          if (s.all_emotions) { emotionHistory.push({ index, ...s.all_emotions }); used = true; }
          if (s.weights) { personalityHistory.push({ index, ...s.weights }); used = true; }
          if (used) index++;
        });
        setTrend({ engagementHistory, emotionHistory, personalityHistory });
      })
      .catch(err => console.error('Failed to fetch trend history:', err));
  }, []);

  useEffect(() => {
    if (isSuperUser) {
        axios.get(`${API_BASE_URL}/api/chat/reflexion/history?limit=50`)
            .then(res => {
                setReflexionData(res.data);
            })
            .catch(err => {
                console.error("Failed to fetch reflexion history:", err);
            });
    }
  }, [isSuperUser]);

  // 跨会话历史与实时累积取更完整的那份:
  //   打开面板时用跨会话历史(全量);
  //   对话进行中 visualState 会持续追加,超过历史长度后以它为准,保证新回合即时可见。
  const pick = (key: 'engagementHistory' | 'emotionHistory' | 'personalityHistory') => {
    const live = (visualState as any)[key] || [];
    const hist = (trend as any)[key] || [];
    return live.length > hist.length ? live : hist;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', paddingRight: '10px' }}>
      <div style={{ background: colorBgContainer, padding: 24, borderRadius: borderRadiusLG }}>
        <Title level={5}>伴侣当前人格状态</Title>
        <StateVisualizer 
            emotions={visualState.emotions} 
            personality={visualState.personality} 
            weights={visualState.weights} 
            engagementHistory={visualState.engagementHistory}
            emotionHistory={visualState.emotionHistory}
        />
      </div>
      
      <div style={{ background: colorBgContainer, borderRadius: borderRadiusLG, overflow: 'hidden' }}>
        <CommunicationAnalysisCard logs={logs} latestUserMessageId={latestUserMessageId} />
      </div>

      {isSuperUser && (
        <>
            <div style={{ background: colorBgContainer, padding: 24, borderRadius: borderRadiusLG }}>
                <PersonalityTrendChart personalityHistory={pick('personalityHistory')} />
            </div>

            <div style={{ background: colorBgContainer, padding: 24, borderRadius: borderRadiusLG }}>
                <EmotionTrendChart emotionHistory={pick('emotionHistory')} />
            </div>

            <div style={{ background: colorBgContainer, padding: 24, borderRadius: borderRadiusLG }}>
                <EngagementChart engagementHistory={pick('engagementHistory')} />
            </div>

            <div style={{ background: colorBgContainer, padding: 24, borderRadius: borderRadiusLG }}>
                <AiResponseEvaluationChart data={reflexionData} />
            </div>
        </>
      )}
    </div>
  );
};

export default AnalysisDashboard;
