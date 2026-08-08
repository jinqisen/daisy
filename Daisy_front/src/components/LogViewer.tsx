import React, { useEffect, useRef } from 'react';

interface LogEntry {
  timestamp: string;
  type: string;
  title: string;
  content: any;
}

interface LogViewerProps {
  logs: LogEntry[];
}

const LogViewer: React.FC<LogViewerProps> = ({ logs }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when logs update
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'emotion': return '#ff00ff'; // Magenta
      case 'personality': return '#bd93f9'; // Purple
      case 'llm': return '#8be9fd'; // Cyan
      case 'error': return '#ff5555'; // Red
      default: return '#50fa7b'; // Green
    }
  };

  const formatTimestamp = (timestamp: unknown) => {
    if (typeof timestamp !== 'string' || !timestamp) {
      return '--:--:--';
    }
    return timestamp.split('T')[1]?.split('.')[0] || timestamp;
  };

  const getDisplayType = (log: any) => {
    if (typeof log?.type === 'string' && log.type.trim()) {
      return log.type.trim();
    }
    if (typeof log?.node_id === 'string' && log.node_id.trim()) {
      return log.node_id.trim();
    }
    if (log?.best_match && log?.reasoning) {
      return 'analysis';
    }
    return 'log';
  };

  const getDisplayTitle = (log: any) => {
    if (typeof log?.title === 'string' && log.title.trim()) {
      return log.title;
    }
    if (typeof log?.node_id === 'string' && log.node_id.trim()) {
      return log.node_id;
    }
    if (log?.best_match && log?.reasoning) {
      return 'Communication Analysis';
    }
    return 'System Event';
  };

  const getDisplayContent = (log: any) => {
    if (log?.content !== undefined) {
      return log.content;
    }
    return log;
  };

  return (
    <div style={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column', 
      background: '#1e1e1e', // VS Code-like dark background
      fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace",
      color: '#d4d4d4',
      borderRadius: '8px',
      overflow: 'hidden',
      border: '1px solid #333',
      boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
    }}>
      {/* Terminal Header */}
      <div style={{ 
        background: '#2d2d2d', 
        padding: '8px 16px', 
        borderBottom: '1px solid #333',
        display: 'flex',
        alignItems: 'center',
        gap: '8px'
      }}>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f56' }}></div>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ffbd2e' }}></div>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#27c93f' }}></div>
        <span style={{ marginLeft: '10px', fontSize: '12px', color: '#aaa' }}>system_monitor.log</span>
      </div>

      {/* Terminal Body */}
      <div style={{ 
        height: 'calc(100vh - 60px)', 
        overflowY: 'auto', 
        padding: '16px',
        fontSize: '13px',
        lineHeight: '1.5'
      }}>
        {logs.length === 0 ? (
          <div style={{ color: '#666' }}>
            $ waiting for system events...<br/>
            <span className="blinking-cursor">_</span>
          </div>
        ) : (
          logs.map((log, index) => {
            const displayType = getDisplayType(log);
            const displayTitle = getDisplayTitle(log);
            const displayContent = getDisplayContent(log);

            return (
            <div key={index} style={{ marginBottom: '12px' }}>
              <div>
                <span style={{ color: '#666' }}>[{formatTimestamp(log?.timestamp)}]</span>
                <span style={{ color: getTypeColor(displayType), fontWeight: 'bold', marginLeft: '8px' }}>
                  {displayType.toUpperCase()}
                </span>
                <span style={{ color: '#fff', marginLeft: '8px' }}>{displayTitle}</span>
              </div>
              <div style={{ paddingLeft: '20px', color: '#a9b7c6', marginTop: '4px' }}>
                {typeof displayContent === 'string' ? (
                  <div>{displayContent}</div>
                ) : (
                  <pre style={{ 
                    margin: 0, 
                    fontFamily: 'inherit', 
                    whiteSpace: 'pre-wrap', 
                    wordBreak: 'break-all',
                    color: '#888' 
                  }}>
                    {JSON.stringify(displayContent, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          )})
        )}
        <div ref={bottomRef} />
        {logs.length > 0 && (
          <div style={{ marginTop: '10px' }}>
            <span style={{ color: '#50fa7b' }}>➜</span> <span className="blinking-cursor">_</span>
          </div>
        )}
      </div>
      <style>{`
        .blinking-cursor {
          animation: blink 1s step-end infinite;
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        /* Custom Scrollbar for dark theme */
        ::-webkit-scrollbar {
          width: 10px;
          height: 10px;
        }
        ::-webkit-scrollbar-track {
          background: #1e1e1e; 
        }
        ::-webkit-scrollbar-thumb {
          background: #444; 
          border-radius: 5px;
        }
        ::-webkit-scrollbar-thumb:hover {
          background: #555; 
        }
      `}</style>
    </div>
  );
};

export default LogViewer;
