import React, { useEffect, useState, useRef } from 'react';
import { usePipecatClient, usePipecatClientMediaTrack } from '@pipecat-ai/client-react';
import {
  ClientStatus,
  HighlightOverlay,
} from '@pipecat-ai/voice-ui-kit';
import { Plasma } from '@pipecat-ai/voice-ui-kit/webgl';
import type { PipecatBaseChildProps } from '@pipecat-ai/voice-ui-kit';
import type { PlasmaRef } from '@pipecat-ai/voice-ui-kit/webgl';
import { CONVERSATION_INFO_DISPLAYED, type TopicInfo } from '../conversationInfoDisplayed';

interface CourseState {
  all_topics: string[];
  discussed_topics: string[];
  responses: Record<string, { interested: boolean }>;
  remaining_topics: string[];
  current_topics: string[];
  current_node: string;
  progress: string;
}

interface TranscriptMessage {
  speaker: 'user' | 'bot';
  text: string;
  timestamp: number;
}

const getTopicInfo = (topic: string): TopicInfo => {
  return CONVERSATION_INFO_DISPLAYED.topics[topic] || {
    description: "Course information",
    details: [],
    link: "",
    image: ""
  };
};

interface ShowcaseLayoutProps extends Partial<PipecatBaseChildProps> {
  courseState?: CourseState;
  transcripts?: { user: string; bot: string };
  isBotSpeaking?: boolean;
  streamingUserText?: string;
  isUserSpeaking?: boolean;
  handleConnect?: () => Promise<void>;
}

const subtleConfig = {
  backgroundColor: "#111827",
  ringBounce: 0.15, ringAmplitude: 0.08, ringThicknessAudio: 4,
  audioSensitivity: 0.3, plasmaVolumeReactivity: 0.4, effectScale: 0.45,
  ringDistance: 0, ringVariance: 0.2, ringVisibility: 0.6, ringSegments: 5,
  ringThickness: 3, ringSpread: 0.06, colorCycleSpeed: 0.15,
  intensity: 0.7, radius: 1.0, glowFalloff: 1, glowThreshold: 0,
  plasmaSpeed: 0.12, rayLength: 0.6,
  color1: "#6b7280", color2: "#4b5563", color3: "#374151"
};

const activeConfig = {
  backgroundColor: "#111827",
  ringBounce: 0.4, ringAmplitude: 0.15, ringThicknessAudio: 15,
  audioSensitivity: 1.8, plasmaVolumeReactivity: 1.8, effectScale: 0.55,
  ringDistance: 0, ringVariance: 0.35, ringVisibility: 0.32, ringSegments: 6,
  ringThickness: 4, ringSpread: 0.1, colorCycleSpeed: 0.25,
  intensity: 1.3, radius: 1.0, glowFalloff: 1.5, glowThreshold: 0,
  plasmaSpeed: 0.22, rayLength: 1.0,
  color1: "#22d3ee", color2: "#34d399", color3: "#818cf8"
};

const ShowcaseLayout: React.FC<ShowcaseLayoutProps> = ({
  handleConnect,
  courseState = {
    all_topics: [],
    discussed_topics: [],
    responses: {},
    remaining_topics: [],
    current_topics: [],
    current_node: 'initial',
    progress: '0/3'
  },
  transcripts = { user: '', bot: '' },
  isBotSpeaking = false,
  isUserSpeaking = false,
}) => {
  const [transcriptHistory, setTranscriptHistory] = useState<TranscriptMessage[]>([]);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const [conversationState, setConversationState] = useState<'idle' | 'listening' | 'thinking'>('idle');
  const prevIsUserSpeaking = useRef(false);

  useEffect(() => {
    if (!prevIsUserSpeaking.current && isUserSpeaking) {
      setConversationState('listening');
    } else if (prevIsUserSpeaking.current && !isUserSpeaking) {
      setConversationState('thinking');
    }
    prevIsUserSpeaking.current = isUserSpeaking;
  }, [isUserSpeaking]);

  useEffect(() => {
    if (conversationState === 'thinking' && transcriptHistory.length > 0) {
      const last = transcriptHistory[transcriptHistory.length - 1];
      if (last?.speaker === 'bot') {
        setConversationState('idle');
      }
    }
  }, [transcriptHistory, conversationState]);

  useEffect(() => {
    if (transcripts.user && transcripts.user.trim() && !isUserSpeaking) {
      setTranscriptHistory(prev => {
        const lastUserMsg = [...prev].reverse().find(m => m.speaker === 'user');
        if (!lastUserMsg || lastUserMsg.text !== transcripts.user) {
          return [...prev, { speaker: 'user', text: transcripts.user, timestamp: Date.now() }];
        }
        return prev;
      });
    }
  }, [transcripts.user, isUserSpeaking]);

  const lastProcessedTts = useRef('');
  useEffect(() => {
    if (transcripts.bot && transcripts.bot.trim() && transcripts.bot !== lastProcessedTts.current) {
      lastProcessedTts.current = transcripts.bot;
      setTranscriptHistory(prev => {
        const lastBotMsg = [...prev].reverse().find(m => m.speaker === 'bot');
        if (lastBotMsg && lastBotMsg.text === transcripts.bot) return prev;
        return [...prev, { speaker: 'bot', text: transcripts.bot, timestamp: Date.now() }];
      });
    }
  }, [transcripts.bot]);

  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, [transcriptHistory]);

  const client = usePipecatClient();
  const transportState = client?.state ?? 'disconnected';
  const botAudioTrack = usePipecatClientMediaTrack("audio", "bot");
  const plasmaRef = useRef<PlasmaRef>(null);

  const [micBars, setMicBars] = useState<number[]>(Array(32).fill(5));
  const [botBars, setBotBars] = useState<number[]>(Array(32).fill(5));

  useEffect(() => {
    if (!botAudioTrack) return;

    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.5;
    const dataArray = new Uint8Array(analyser.fftSize);

    const stream = new MediaStream([botAudioTrack]);
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    let animationId: number;
    const animate = () => {
      analyser.getByteTimeDomainData(dataArray);

      const bars: number[] = [];
      const segmentSize = Math.floor(dataArray.length / 32);

      for (let i = 0; i < 32; i++) {
        let sum = 0;
        for (let j = 0; j < segmentSize; j++) {
          const val = Math.abs((dataArray[i * segmentSize + j] - 128) / 128);
          sum += val * val;
        }
        const rms = Math.sqrt(sum / segmentSize);
        bars.push(Math.max(5, Math.min(95, rms * 400)));
      }

      setBotBars(bars);
      animationId = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (animationId) cancelAnimationFrame(animationId);
      source.disconnect();
      audioContext.close();
    };
  }, [botAudioTrack]);

  useEffect(() => {
    if (transportState !== 'ready') return;

    let audioContext: AudioContext;
    let analyser: AnalyserNode;
    let animationId: number;

    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
      audioContext = new AudioContext();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.5;
      const dataArray = new Uint8Array(analyser.fftSize);

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      const animate = () => {
        analyser.getByteTimeDomainData(dataArray);

        const bars: number[] = [];
        const segmentSize = Math.floor(dataArray.length / 32);

        for (let i = 0; i < 32; i++) {
          let sum = 0;
          for (let j = 0; j < segmentSize; j++) {
            const val = Math.abs((dataArray[i * segmentSize + j] - 128) / 128);
            sum += val * val;
          }
          const rms = Math.sqrt(sum / segmentSize);
          bars.push(Math.max(5, Math.min(95, rms * 400)));
        }

        setMicBars(bars);
        animationId = requestAnimationFrame(animate);
      };

      animate();
    });

    return () => {
      if (animationId) cancelAnimationFrame(animationId);
      if (audioContext) audioContext.close();
    };
  }, [transportState]);

  useEffect(() => {
    if (plasmaRef.current) {
      plasmaRef.current.updateConfig(transportState === 'ready' ? activeConfig : subtleConfig);
    }
  }, [transportState]);

  useEffect(() => {
    if (plasmaRef.current && transportState === 'ready') {
      if (conversationState === 'listening') {
        plasmaRef.current.updateConfig({
          color1: "#9333ea", color2: "#7c3aed", color3: "#a855f7",
        });
      } else if (conversationState === 'thinking') {
        plasmaRef.current.updateConfig({
          color1: "#22c55e", color2: "#16a34a", color3: "#4ade80",
        });
      } else {
        plasmaRef.current.updateConfig({
          color1: "#22d3ee", color2: "#34d399", color3: "#818cf8",
        });
      }
    }
  }, [conversationState, transportState]);

  useEffect(() => {
    if (transportState === 'ready') {
      setTranscriptHistory([]);
      lastProcessedTts.current = '';
    }
  }, [transportState]);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header
        className="relative border-b border-purple-700 bg-cover bg-center"
        style={{ backgroundImage: "url('https://moodle.tuni.fi/pluginfile.php/1/theme_maisteriboost/slide1image/0/Opiskelijat72scalepurplemod.jpg')" }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-indigo-950/90 to-purple-950/90"></div>
        <div className="relative z-10 flex items-center justify-between p-4">
          <h1 className="text-xl font-semibold text-white">{CONVERSATION_INFO_DISPLAYED.pageTitle}</h1>
          <div className="flex items-center gap-4">
            <ClientStatus />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto p-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6">

          {/* Left - Visualizer + Controls */}
          <div className="lg:col-span-3 space-y-6">
            {/* Visualizer */}
            <div className="bg-gray-900 backdrop-blur-sm rounded-lg p-4 border border-purple-800/40 shadow-lg flex flex-col">
              <h2 className="text-lg font-bold mb-3 text-purple-400 text-center">Visualizer</h2>
              <div className="relative aspect-square flex items-center justify-center border-2 border-purple-800 rounded-lg bg-gray-950">
                {CONVERSATION_INFO_DISPLAYED.visualizerType === 'plasma' ? (
                  <>
                    <Plasma
                      ref={plasmaRef}
                      audioTrack={transportState === 'ready' ? botAudioTrack : undefined}
                      alpha={true}
                      initialConfig={transportState === 'ready' ? activeConfig : subtleConfig}
                      className="absolute inset-0 pointer-events-none animate-fade-in z-0"
                    />
                    {transportState === 'ready' && (
                      <div className="absolute bottom-4 left-0 right-0 flex justify-center z-10">
                        <div className="text-sm font-medium animate-pulse">
                          {!isBotSpeaking && conversationState === 'listening' && (
                            <span className="text-purple-400">Listening...</span>
                          )}
                          {!isBotSpeaking && conversationState === 'thinking' && (
                            <span className="text-green-400">Thinking...</span>
                          )}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="absolute inset-0 flex flex-col p-4">
                    <div className="flex-1 flex items-end justify-center gap-1">
                      {micBars.map((height, i) => (
                        <div
                          key={`mic-${i}`}
                          className="w-2 bg-purple-500 rounded-t transition-all duration-100"
                          style={{
                            height: `${height}%`,
                            opacity: transportState === 'ready' ? 1 : 0.3
                          }}
                        />
                      ))}
                    </div>
                    <div className="text-xs text-center py-2 text-purple-400 font-medium">Your Voice</div>
                    <div className="flex-1 flex items-start justify-center gap-1">
                      {botBars.map((height, i) => (
                        <div
                          key={`bot-${i}`}
                          className="w-2 bg-green-500 rounded-b transition-all duration-100"
                          style={{
                            height: `${height}%`,
                            opacity: transportState === 'ready' ? 1 : 0.3
                          }}
                        />
                      ))}
                    </div>
                    <div className="text-xs text-center py-2 text-green-400 font-medium">Bot Voice</div>
                  </div>
                )}
              </div>
            </div>

            {/* Connect button - only when disconnected */}
            {transportState !== 'ready' && (
              <div className="bg-gray-900 backdrop-blur-sm rounded-lg p-6 border border-indigo-700/40 shadow-lg">
                <div className="mb-4 text-center">
                  <h2 className="text-lg font-bold text-indigo-300">HTI.560</h2>
                  <p className="text-sm text-gray-400">Conversational Interaction with AI</p>
                </div>
                <div className="px-3 py-1 mb-4 bg-gray-800 border border-gray-600 rounded-lg">
                  <p className="text-xs text-gray-300 text-center">
                    Have your mic ready and just speak naturally!
                  </p>
                </div>
                <button
                  onClick={handleConnect}
                  className="w-full px-4 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-lg transition-all transform hover:scale-105 font-medium shadow-lg"
                >
                  Start voice interaction
                </button>
              </div>
            )}

            {/* Current Turn */}
            {transportState === 'ready' && (
              <div className="bg-gray-900 backdrop-blur-sm rounded-lg p-4 border border-purple-800/40 shadow-lg">
                <h2 className="text-sm font-bold mb-3 text-purple-400 text-center">Current Turn</h2>
                <div className="space-y-3">
                  <div>
                    <div className="text-xs text-gray-400 mb-1">Assistant:</div>
                    <div className="text-sm p-2 rounded-lg min-h-[36px] border bg-gray-800 border-gray-700">
                      <span className="text-gray-100">{transcripts.bot || <span className="text-gray-500 italic text-xs">Waiting...</span>}</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400 mb-1">
                      You{isUserSpeaking ? ' - Speaking...' : ''}:
                    </div>
                    <div className="text-sm p-2 rounded-lg min-h-[36px] border bg-gray-800 border-gray-700">
                      <span className="text-gray-100">{transcripts.user || <span className="text-gray-500 italic text-xs">Waiting...</span>}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Center - Conversation History */}
          <div className="lg:col-span-5">
            <div className="bg-gray-900 backdrop-blur-sm rounded-lg p-5 border border-purple-800/40 shadow-lg h-full flex flex-col">
              <h2 className="text-xl font-bold mb-4 text-purple-400 text-center">💬 Conversation</h2>
              {transportState === 'ready' ? (
                <div className="flex-1 overflow-y-auto min-h-[600px]" ref={scrollContainerRef}>
                  {transcriptHistory.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-500">
                      <div className="text-4xl mb-4">🎙️</div>
                      <div className="text-base font-semibold mb-1">Session Active</div>
                      <div className="text-sm">Start speaking to begin the conversation...</div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {[...transcriptHistory].reverse().map((msg, idx) => (
                        <div key={idx} className={`flex ${msg.speaker === 'user' ? 'justify-end' : 'justify-start'}`}>
                          <div className={`max-w-[85%] p-3 rounded-xl ${
                            msg.speaker === 'user'
                              ? 'bg-indigo-950/60 border border-indigo-700'
                              : 'bg-gray-800 border border-gray-700'
                          }`}>
                            <div className="text-xs text-gray-400 font-semibold mb-1">
                              {msg.speaker === 'user' ? '🧑 You' : '🤖 Assistant'}
                            </div>
                            <div className="text-sm text-gray-100 leading-relaxed">{msg.text}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center flex-1 text-gray-500 min-h-[600px]">
                  <div className="text-4xl mb-4">🔌</div>
                  <p className="text-sm">Connect to start the conversation</p>
                </div>
              )}
            </div>
          </div>

          {/* Right - Course Topics */}
          <div className="lg:col-span-4">
            <div className="bg-gray-900 backdrop-blur-sm rounded-lg p-4 border border-indigo-700/40 shadow-lg h-full">
              <h2 className="text-lg font-bold mb-1 text-center text-indigo-300">
                {courseState.current_node === 'questions' ? 'Course Info - Q&A Mode' : 'Ask about Course Topics'}
              </h2>
              <p className="text-xs text-gray-500 text-center mb-4">
                {courseState.current_node === 'questions'
                  ? 'Ask me anything about the course!'
                  : 'What would you like to study?'}
              </p>

              <div className={courseState.current_node === 'questions' ? 'w-full' : 'space-y-2'}>
                {courseState.current_node === 'questions' ? (
                  courseState.current_topics
                    .map(topic => {
                      const topicInfo = getTopicInfo(topic);
                      return (
                        <div key={topic} className="w-full p-4 rounded-lg bg-gray-800 border-2 border-green-600">
                          <div className="flex items-center gap-2 mb-3">
                            <h3 className="font-semibold text-base text-green-400">{topic}</h3>
                          </div>
                          <p className="text-sm text-gray-300 mb-3">{topicInfo.description}</p>
                          {topicInfo.image && (
                            <img
                              src={topicInfo.image}
                              alt={topic}
                              className="w-full h-auto rounded-lg mb-3 max-h-64 object-cover"
                            />
                          )}
                          <ul className="text-sm text-gray-400 space-y-1 mb-3">
                            {topicInfo.details.map((detail, idx) => (
                              <li key={idx}>- {detail}</li>
                            ))}
                          </ul>
                          {topicInfo.link && (
                            <a
                              href={topicInfo.link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-block px-3 py-1 text-sm text-blue-400 hover:text-blue-300 bg-blue-950/50 rounded-lg border border-blue-700"
                            >
                              Open in Moodle
                            </a>
                          )}
                        </div>
                      );
                    })
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {courseState.all_topics.map(topic => {
                      const isDiscussed = courseState.discussed_topics.includes(topic);
                      const isInterested = courseState.responses[topic]?.interested;

                      let bgClass = 'bg-purple-950/40 border border-purple-700/50';
                      let textColor = 'text-gray-200';
                      let icon = 'o';

                      if (isDiscussed && isInterested) {
                        bgClass = 'bg-green-950/40 border border-green-600';
                        textColor = 'text-green-300';
                        icon = 'v';
                      }

                      return (
                        <div key={topic} className={`p-3 rounded-lg transition-all ${bgClass}`}>
                          <div className="flex items-center gap-2">
                            <span className="text-lg font-bold">{icon}</span>
                            <p className={`text-sm ${textColor}`}>{topic}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {transportState === 'ready' && <HighlightOverlay />}
    </div>
  );
};

export default ShowcaseLayout;