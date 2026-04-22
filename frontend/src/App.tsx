import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react';
import {
  PipecatAppBase,
  ThemeProvider,
} from '@pipecat-ai/voice-ui-kit';
import ShowcaseLayout from './components/ShowcaseLayout';

interface CourseState {
  all_topics: string[];
  discussed_topics: string[];
  responses: Record<string, { interested: boolean }>;
  remaining_topics: string[];
  current_topics: string[];
  current_node: string;
  progress: string;
}

function App() {
  const [courseState, setCourseState] = useState<CourseState>({
    all_topics: [],
    discussed_topics: [],
    responses: {},
    remaining_topics: [],
    current_topics: [],
    current_node: 'initial',
    progress: '0/3'
  });

  const [transcripts, setTranscripts] = useState<{user: string, bot: string}>({
    user: '',
    bot: ''
  });

  const [isBotSpeaking, setIsBotSpeaking] = useState(false);
  const [streamingUserText, setStreamingUserText] = useState('');
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);
  const streamingUserTextRef = useRef('');

  const handleServerMessage = useCallback((message: any) => {
  const data = message?.data ?? message;

  if (data?.type === 'conversation_state_update') {
    setCourseState(prev => ({
      ...prev,
      all_topics: data.all_topics ?? prev.all_topics,
      discussed_topics: data.discussed_topics ?? prev.discussed_topics,
      responses: data.responses ?? prev.responses,
      remaining_topics: data.remaining_topics ?? prev.remaining_topics,
      current_topics: data.current_topics ?? prev.current_topics,
      current_node: data.current_node ?? prev.current_node,
      progress: data.progress ?? prev.progress,
    }));
  }
}, []);

  const handleUserTranscript = useCallback((data: any) => {
    const isFinal = data?.final !== false;
    if (data?.text) {
      if (!isFinal) {
        setStreamingUserText(data.text);
        streamingUserTextRef.current = data.text;
        setIsUserSpeaking(true);
      } else {
        setTranscripts(prev => ({ ...prev, user: data.text }));
        setStreamingUserText('');
        streamingUserTextRef.current = '';
        setIsUserSpeaking(false);
      }
    }
  }, []);

  const handleBotTtsText = useCallback((data: any) => {
    if (data?.text && data.text.trim()) {
      setTranscripts(prev => ({ ...prev, bot: data.text }));
    }
  }, []);

  const handleBotStartedSpeaking = useCallback(() => {
    setIsBotSpeaking(true);
  }, []);

  const handleBotStoppedSpeaking = useCallback(() => {
    setIsBotSpeaking(false);
  }, []);

  const handleUserStartedSpeaking = useCallback(() => {
    setIsUserSpeaking(true);
  }, []);

  const handleConnected = useCallback(() => {
    setTranscripts({ user: '', bot: '' });
    setStreamingUserText('');
    setIsUserSpeaking(false);
    setIsBotSpeaking(false);
  }, []);

  const handleDisconnected = useCallback(() => {
    setStreamingUserText('');
    setIsUserSpeaking(false);
    setIsBotSpeaking(false);
  }, []);

  // Safety timeout: if user speaking state gets stuck, clear after 5s
  useEffect(() => {
    if (isUserSpeaking) {
      const timeout = setTimeout(() => {
        if (streamingUserTextRef.current) {
          setTranscripts(prev => ({ ...prev, user: streamingUserTextRef.current }));
        }
        setStreamingUserText('');
        streamingUserTextRef.current = '';
        setIsUserSpeaking(false);
      }, 5000);
      return () => clearTimeout(timeout);
    }
  }, [isUserSpeaking]);

  const clientOptions = useMemo(() => ({
    enableMic: true,
    enableCam: false,
    callbacks: {
      onServerMessage: handleServerMessage,
      onUserTranscript: handleUserTranscript,
      onBotTtsText: handleBotTtsText,
      onBotStartedSpeaking: handleBotStartedSpeaking,
      onBotStoppedSpeaking: handleBotStoppedSpeaking,
      onUserStartedSpeaking: handleUserStartedSpeaking,
      onConnected: handleConnected,
      onDisconnected: handleDisconnected,
    },
  }), [handleServerMessage, handleUserTranscript, handleBotTtsText, handleBotStartedSpeaking, handleBotStoppedSpeaking, handleUserStartedSpeaking, handleConnected, handleDisconnected]);

  const connectParams = useMemo(() => ({}), []);

  return (
    <ThemeProvider defaultTheme="dark" storageKey="voice-ui-theme">
      <PipecatAppBase
        transportType="smallwebrtc"
        clientOptions={clientOptions as any}
        connectParams={connectParams}
      >
        {({ client }) => {
          const handleConnect = async () => {
            try {
              if (client.state !== 'disconnected') {
                try {
                  await client.disconnect();
                } catch (e) {
                  console.warn('Disconnect failed during reconnect:', e);
                }
                await new Promise(resolve => setTimeout(resolve, 500));
              }
              setTranscripts({ user: '', bot: '' });
              await client.startBotAndConnect({
                endpoint: '/api/start',
                requestData: {}
              });
            } catch {
              if (client.state === 'ready' || client.state === 'connecting') {
                try {
                  await client.disconnect();
                } catch (e) {
                  console.warn('Disconnect failed during error recovery:', e);
                }
              }
            }
          };

          return (
            <ShowcaseLayout
              handleConnect={handleConnect}
              courseState={courseState}
              transcripts={transcripts}
              isBotSpeaking={isBotSpeaking}
              streamingUserText={streamingUserText}
              isUserSpeaking={isUserSpeaking}
            />
          );
        }}
      </PipecatAppBase>
    </ThemeProvider>
  );
}

export default App;
