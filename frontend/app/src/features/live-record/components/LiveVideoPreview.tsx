import React, { useState, useEffect } from 'react';
import {
  Bot,
  Terminal as TerminalIcon,
  Code2,
  Globe,
  GitBranch,
  Sparkles,
  Layers,
  ArrowRight,
} from 'lucide-react';

export type AIAgentScreenMode = 'host' | 'code' | 'terminal' | 'browser' | 'swarm';

export interface LiveVideoPreviewProps {
  isRecording: boolean;
  recordingTimeFormatted: string;
  resolution?: string;
  fps?: number;
  activeSceneIndex?: number;
  teleprompterText?: string;
  /** Real sidecar preview (data:image/jpeg;base64) — overlays the simulation when present. */
  previewDataUrl?: string;
}

export const LiveVideoPreview: React.FC<LiveVideoPreviewProps> = ({
  isRecording,
  recordingTimeFormatted,
  resolution = '1080p',
  fps = 60,
  activeSceneIndex = 1,
  teleprompterText = '',
  previewDataUrl,
}) => {
  const [screenMode, setScreenMode] = useState<AIAgentScreenMode>('host');
  const [terminalLogIndex, setTerminalLogIndex] = useState<number>(4);

  // Synchronize screen mode with active scene if changed
  useEffect(() => {
    switch (activeSceneIndex) {
      case 0:
        setScreenMode('host');
        break;
      case 1:
        setScreenMode('code');
        break;
      case 2:
        setScreenMode('browser');
        break;
      case 3:
        setScreenMode('terminal');
        break;
      case 4:
        setScreenMode('swarm');
        break;
      default:
        setScreenMode('code');
    }
  }, [activeSceneIndex]);

  // Animated code typing simulation
  useEffect(() => {
    if (!isRecording) return;
    const interval = setInterval(() => {
      setTerminalLogIndex((prev) => (prev >= 11 ? 3 : prev + 1));
    }, 1800);
    return () => clearInterval(interval);
  }, [isRecording]);

  const terminalLogs = [
    { type: 'info', text: '$ windagent workflow run episode_02_video --mode=real' },
    { type: 'success', text: '[orchestrator] Initializing Agent Swarm: Planner, Coder, Reviewer, Renderer' },
    { type: 'info', text: '[planner] Generating 16 recording passes from screenplay bible...' },
    { type: 'success', text: '✓ PASS_01_COLD_OPEN: Scene validated (1080p, 60fps, 16:9)' },
    { type: 'info', text: '[coder] Writing windagent_tools/code_video/recording/passes.py' },
    { type: 'success', text: '✓ PASS_02_AGENT_CORE: Compilation complete (0 warnings)' },
    { type: 'info', text: '[terminal] Running pytest test_phase14_web_desktop_parity.py' },
    { type: 'success', text: '✓ 14/14 tests passed in 0.94s (100% boundary parity)' },
    { type: 'info', text: '[renderer] Compositing audio cues & teleprompter timeline...' },
    { type: 'success', text: '✓ Exporting stream: D:\\WindAgent\\Recordings\\WindAgent_Demo_Part1.mp4' },
    { type: 'info', text: '[hermes] Heartbeat online: 4.6/24 Cores | GPU: RTX 3060 (32%)' },
  ];

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        aspectRatio: '16 / 9',
        borderRadius: '16px',
        backgroundColor: '#060b14',
        border: '1px solid rgba(59, 130, 246, 0.3)',
        overflow: 'hidden',
        boxShadow: '0 12px 36px -8px rgba(0, 0, 0, 0.7), 0 0 24px rgba(59, 130, 246, 0.15)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* ========================================================================= */}
      {/* SCREEN VIEWPORTS (AI AGENT OPERATION SCREENS)                             */}
      {/* ========================================================================= */}

      {/* Real sidecar preview frame (≤1280×720 JPEG @ ≤2FPS, Principle E).
          Rendered above the simulation layers but below the overlay badges. */}
      {previewDataUrl && (
        <img
          src={previewDataUrl}
          alt="Live preview từ recording engine"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            zIndex: 4,
          }}
        />
      )}

      {/* Mode 1: AI STUDIO HOST STAGE */}
      {screenMode === 'host' && (
        <div
          style={{
            width: '100%',
            height: '100%',
            position: 'relative',
            background: 'radial-gradient(ellipse at 50% 40%, #172554 0%, #0c1527 50%, #060b14 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
          }}
        >
          {/* Neon Glow Sign in background */}
          <div
            style={{
              position: 'absolute',
              top: '20%',
              left: '26%',
              transform: 'translate(-50%, -50%)',
              padding: '12px 24px',
              borderRadius: '12px',
              border: '2px solid rgba(59, 130, 246, 0.5)',
              background: 'rgba(15, 23, 42, 0.6)',
              backdropFilter: 'blur(8px)',
              boxShadow: '0 0 35px rgba(59, 130, 246, 0.35), inset 0 0 20px rgba(59, 130, 246, 0.2)',
              textAlign: 'center',
              zIndex: 1,
            }}
          >
            <div
              style={{
                fontSize: '18px',
                fontWeight: 800,
                color: '#ffffff',
                letterSpacing: '1px',
                textShadow: '0 0 10px #3b82f6, 0 0 20px #2563eb',
              }}
            >
              WindAgent
            </div>
            <div
              style={{
                fontSize: '11px',
                fontWeight: 700,
                color: '#93c5fd',
                letterSpacing: '2.5px',
                textTransform: 'uppercase',
              }}
            >
              Studio
            </div>
          </div>

          {/* AI Presenter Illustration / SVG Vector Studio Art */}
          <svg
            viewBox="0 0 800 450"
            style={{
              width: '100%',
              height: '100%',
              position: 'absolute',
              top: 0,
              left: 0,
              zIndex: 2,
            }}
          >
            <defs>
              <linearGradient id="hoodieGrad2" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#1e293b" />
                <stop offset="100%" stopColor="#0f172a" />
              </linearGradient>
              <linearGradient id="skinGrad2" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#ffdfc4" />
                <stop offset="100%" stopColor="#e2b997" />
              </linearGradient>
              <linearGradient id="tableGrad2" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#1e293b" />
                <stop offset="100%" stopColor="#090d16" />
              </linearGradient>
            </defs>

            {/* Studio Desk / Table Surface */}
            <path d="M 0 380 L 800 380 L 800 450 L 0 450 Z" fill="url(#tableGrad2)" />
            <line x1="0" y1="380" x2="800" y2="380" stroke="#3b82f6" strokeWidth="1.5" strokeOpacity="0.4" />

            {/* Presenter Body (Hoodie) */}
            <path
              d="M 230 380 Q 250 280 320 250 L 360 250 Q 370 240 400 240 Q 430 240 440 250 L 480 250 Q 550 280 570 380 Z"
              fill="url(#hoodieGrad2)"
              stroke="#334155"
              strokeWidth="2"
            />
            <text x="400" y="325" fill="#f8fafc" fontSize="13" fontWeight="bold" textAnchor="middle" opacity="0.85" letterSpacing="1">
              WindAgent
            </text>

            {/* Neck & Head */}
            <rect x="382" y="210" width="36" height="45" rx="6" fill="url(#skinGrad2)" />
            <ellipse cx="400" cy="170" rx="42" ry="52" fill="url(#skinGrad2)" />
            <path
              d="M 355 160 Q 355 118 400 118 Q 445 118 445 160 Q 435 130 400 132 Q 365 130 355 160 Z"
              fill="#0f172a"
            />
            {/* Glasses */}
            <rect x="370" y="156" width="24" height="16" rx="4" fill="none" stroke="#0f172a" strokeWidth="2.5" />
            <rect x="406" y="156" width="24" height="16" rx="4" fill="none" stroke="#0f172a" strokeWidth="2.5" />
            <line x1="394" y1="162" x2="406" y2="162" stroke="#0f172a" strokeWidth="2.5" />
            <path d="M 388 194 Q 400 202 412 194" fill="none" stroke="#9a3412" strokeWidth="2" strokeLinecap="round" />

            {/* Gesturing Hands */}
            <path d="M 230 350 Q 210 320 225 295 Q 240 270 260 290 Q 275 310 260 345 Z" fill="url(#skinGrad2)" stroke="#ca8a04" strokeWidth="0.5" />
            <path d="M 570 350 Q 590 320 575 295 Q 560 270 540 290 Q 525 310 540 345 Z" fill="url(#skinGrad2)" stroke="#ca8a04" strokeWidth="0.5" />

            {/* Desk Coffee Cup */}
            <rect x="220" y="340" width="30" height="38" rx="3" fill="#1e293b" stroke="#475569" strokeWidth="1.5" />
            <text x="235" y="364" fill="#60a5fa" fontSize="10" fontWeight="bold" textAnchor="middle">WA</text>

            {/* Studio Laptop with glowing logo */}
            <path d="M 460 380 L 580 380 L 595 320 L 505 320 Z" fill="#1e293b" stroke="#3b82f6" strokeWidth="1" />
            <circle cx="545" cy="350" r="7" fill="none" stroke="#60a5fa" strokeWidth="2" />
            <text x="545" y="354" fill="#93c5fd" fontSize="9" fontWeight="bold" textAnchor="middle">G</text>

            {/* Boom Mic */}
            <line x1="380" y1="280" x2="425" y2="230" stroke="#475569" strokeWidth="6" strokeLinecap="round" />
            <line x1="425" y1="230" x2="465" y2="290" stroke="#475569" strokeWidth="6" strokeLinecap="round" />
            <line x1="465" y1="290" x2="495" y2="380" stroke="#334155" strokeWidth="8" strokeLinecap="round" />
          </svg>

          {/* Subtitle Teleprompter Banner at bottom of Host */}
          <div
            style={{
              position: 'absolute',
              bottom: '50px',
              left: '50%',
              transform: 'translateX(-50%)',
              width: '85%',
              backgroundColor: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(59, 130, 246, 0.4)',
              borderRadius: '10px',
              padding: '8px 16px',
              backdropFilter: 'blur(8px)',
              color: '#f8fafc',
              fontSize: '13px',
              fontWeight: 500,
              textAlign: 'center',
              zIndex: 10,
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.6)',
            }}
          >
            <span style={{ color: '#60a5fa', fontWeight: 700, marginRight: '6px' }}>AI Host:</span>
            {teleprompterText ? teleprompterText.substring(0, 110) + '...' : 'Chào mừng đến với WindAgent Studio — nền tảng điều phối AI Agents.'}
          </div>
        </div>
      )}

      {/* Mode 2: AI CODE STUDIO (Live Coding Simulation) */}
      {screenMode === 'code' && (
        <div
          style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            backgroundColor: '#0d1117',
            fontFamily: 'monospace',
            fontSize: '11px',
            color: '#c9d1d9',
          }}
        >
          {/* File Tree Left Pane */}
          <div
            style={{
              width: '180px',
              backgroundColor: '#010409',
              borderRight: '1px solid #30363d',
              padding: '12px 8px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              fontSize: '11px',
            }}
          >
            <div style={{ color: '#8b949e', fontWeight: 700, textTransform: 'uppercase', fontSize: '9px', marginBottom: '4px' }}>
              📁 WindAgent Workspace
            </div>
            <div style={{ color: '#58a6ff', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>📄</span> live_recorder.py
            </div>
            <div style={{ color: '#8b949e', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>📄</span> agent_swarm.py
            </div>
            <div style={{ color: '#8b949e', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>📄</span> orchestrator.py
            </div>
            <div style={{ color: '#8b949e', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>📄</span> video_pipeline.ts
            </div>

            {/* AI Agent Status Widget */}
            <div
              style={{
                marginTop: 'auto',
                padding: '8px',
                borderRadius: '6px',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                fontSize: '10px',
              }}
            >
              <div style={{ color: '#60a5fa', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Bot size={12} /> AI Coder Active
              </div>
              <div style={{ color: '#94a3b8', marginTop: '2px' }}>Typing pass: 02_CORE</div>
            </div>
          </div>

          {/* Code Editor Main */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Editor Tab Bar */}
            <div
              style={{
                height: '32px',
                backgroundColor: '#010409',
                borderBottom: '1px solid #30363d',
                display: 'flex',
                alignItems: 'center',
                padding: '0 12px',
                gap: '8px',
              }}
            >
              <div
                style={{
                  backgroundColor: '#0d1117',
                  borderTop: '2px solid #58a6ff',
                  padding: '4px 12px',
                  color: '#f0f6fc',
                  fontWeight: 600,
                  fontSize: '11px',
                }}
              >
                live_recorder.py
              </div>
              <span style={{ color: '#8b949e', fontSize: '10px' }}>Python 3.12 (VirtualEnv: .venv)</span>
            </div>

            {/* Code Lines Display */}
            <div
              style={{
                flex: 1,
                padding: '12px 16px',
                overflowY: 'auto',
                lineHeight: '1.6',
                display: 'flex',
                gap: '16px',
              }}
            >
              {/* Line Numbers */}
              <div style={{ color: '#484f58', textAlign: 'right', userSelect: 'none' }}>
                {Array.from({ length: 18 }).map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>

              {/* Code Tokens */}
              <div style={{ color: '#e6edf3' }}>
                <div>
                  <span style={{ color: '#ff7b72' }}>import</span> <span style={{ color: '#ffa657' }}>asyncio</span>
                </div>
                <div>
                  <span style={{ color: '#ff7b72' }}>from</span> <span style={{ color: '#ffa657' }}>windagent_core.recording</span> <span style={{ color: '#ff7b72' }}>import</span> VideoEngine
                </div>
                <div>
                  <span style={{ color: '#ff7b72' }}>from</span> <span style={{ color: '#ffa657' }}>windagent_tools.code_video</span> <span style={{ color: '#ff7b72' }}>import</span> PassCatalog
                </div>
                <div style={{ height: '10px' }} />
                <div>
                  <span style={{ color: '#ff7b72' }}>class</span> <span style={{ color: '#f0883e' }}>AutonomousVideoRecorder</span>:
                </div>
                <div style={{ paddingLeft: '16px' }}>
                  <span style={{ color: '#ff7b72' }}>def</span> <span style={{ color: '#d2a8ff' }}>__init__</span>(self, model: <span style={{ color: '#79c0ff' }}>str</span> = <span style={{ color: '#a5d6ff' }}>"hermes-3-llama-3.1"</span>):
                </div>
                <div style={{ paddingLeft: '32px' }}>
                  self.engine = VideoEngine(resolution=<span style={{ color: '#a5d6ff' }}>"1080p"</span>, fps=<span style={{ color: '#79c0ff' }}>60</span>)
                </div>
                <div style={{ paddingLeft: '32px' }}>
                  self.catalog = PassCatalog.load_canonical()
                </div>
                <div style={{ height: '10px' }} />
                <div style={{ paddingLeft: '16px' }}>
                  <span style={{ color: '#ff7b72' }}>async def</span> <span style={{ color: '#d2a8ff' }}>record_active_scene</span>(self, scene_id: <span style={{ color: '#79c0ff' }}>str</span>) -&gt; <span style={{ color: '#79c0ff' }}>dict</span>:
                </div>
                <div style={{ paddingLeft: '32px', backgroundColor: 'rgba(56, 139, 253, 0.15)', borderLeft: '2px solid #58a6ff', padding: '2px 4px' }}>
                  <span style={{ color: '#8b949e' }}># Autonomous Agent dynamically executing code actions</span>
                </div>
                <div style={{ paddingLeft: '32px' }}>
                  stream = <span style={{ color: '#ff7b72' }}>await</span> self.engine.start_capture_stream(scene_id)
                </div>
                <div style={{ paddingLeft: '32px' }}>
                  <span style={{ color: '#ff7b72' }}>return</span> &#123;<span style={{ color: '#a5d6ff' }}>"status"</span>: <span style={{ color: '#a5d6ff' }}>"recording"</span>, <span style={{ color: '#a5d6ff' }}>"frames"</span>: stream.frame_count&#125;
                  <span
                    style={{
                      display: 'inline-block',
                      width: '8px',
                      height: '14px',
                      backgroundColor: '#58a6ff',
                      marginLeft: '4px',
                      animation: 'pulse 1s infinite',
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Mode 3: AI TERMINAL / CLI */}
      {screenMode === 'terminal' && (
        <div
          style={{
            width: '100%',
            height: '100%',
            backgroundColor: '#090d16',
            padding: '16px',
            fontFamily: 'monospace',
            fontSize: '12px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            overflowY: 'auto',
          }}
        >
          <div style={{ color: '#60a5fa', fontWeight: 700, borderBottom: '1px solid #1e293b', paddingBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TerminalIcon size={14} /> WindAgent Terminal Execution Stream
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '4px' }}>
            {terminalLogs.slice(0, terminalLogIndex).map((log, idx) => (
              <div
                key={idx}
                style={{
                  color: log.type === 'success' ? '#4ade80' : log.text.startsWith('$') ? '#facc15' : '#cbd5e1',
                  lineHeight: '1.4',
                }}
              >
                {log.text}
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#60a5fa' }}>
              <span>$ hermes agent execute --take=active</span>
              <span
                style={{
                  display: 'inline-block',
                  width: '8px',
                  height: '14px',
                  backgroundColor: '#60a5fa',
                  animation: 'pulse 1s infinite',
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Mode 4: AUTONOMOUS BROWSER AGENT */}
      {screenMode === 'browser' && (
        <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', backgroundColor: '#0f172a' }}>
          {/* Browser Navigation Bar */}
          <div
            style={{
              height: '34px',
              backgroundColor: '#1e293b',
              borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
              display: 'flex',
              alignItems: 'center',
              padding: '0 12px',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', gap: '4px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ef4444' }} />
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#eab308' }} />
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#22c55e' }} />
            </div>
            <div
              style={{
                flex: 1,
                backgroundColor: '#090d16',
                borderRadius: '6px',
                padding: '3px 10px',
                fontSize: '11px',
                color: '#94a3b8',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Globe size={11} color="#60a5fa" />
              <span>https://windagent.dev/studio/orchestration</span>
            </div>
            <span style={{ fontSize: '10px', color: '#4ade80', fontWeight: 600 }}>Headless Capture</span>
          </div>

          {/* Browser Content */}
          <div style={{ flex: 1, padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
              🌐 Agent Web Automation & Production Sandbox
            </div>
            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              AI Agent is inspecting DOM nodes, triggering event dispatches, and recording browser interactions.
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginTop: '12px' }}>
              <div style={{ backgroundColor: '#1e293b', padding: '12px', borderRadius: '8px', border: '1px solid #3b82f6' }}>
                <div style={{ color: '#60a5fa', fontWeight: 600, fontSize: '12px' }}>DOM Element #1</div>
                <div style={{ color: '#94a3b8', fontSize: '10px', marginTop: '4px' }}>Click dispatched: Success</div>
              </div>
              <div style={{ backgroundColor: '#1e293b', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 600, fontSize: '12px' }}>Form Input Field</div>
                <div style={{ color: '#94a3b8', fontSize: '10px', marginTop: '4px' }}>Typing payload complete</div>
              </div>
              <div style={{ backgroundColor: '#1e293b', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
                <div style={{ color: '#f8fafc', fontWeight: 600, fontSize: '12px' }}>Screenshot Buffer</div>
                <div style={{ color: '#4ade80', fontSize: '10px', marginTop: '4px' }}>60 FPS capture synced</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Mode 5: AGENT SWARM & FLOW */}
      {screenMode === 'swarm' && (
        <div style={{ width: '100%', height: '100%', backgroundColor: '#090d16', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ color: '#60a5fa', fontWeight: 700, fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <GitBranch size={16} /> Autonomous Agent Swarm Pipeline Graph
          </div>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-around' }}>
            <div style={{ padding: '16px', borderRadius: '12px', backgroundColor: '#1e293b', border: '2px solid #3b82f6', textAlign: 'center', minWidth: '120px' }}>
              <Bot size={24} color="#60a5fa" style={{ margin: '0 auto 6px auto' }} />
              <div style={{ color: '#f8fafc', fontWeight: 700, fontSize: '12px' }}>Planner Agent</div>
              <div style={{ color: '#4ade80', fontSize: '10px' }}>Active (100%)</div>
            </div>
            <ArrowRight size={20} color="#60a5fa" />
            <div style={{ padding: '16px', borderRadius: '12px', backgroundColor: '#1e293b', border: '2px solid #22c55e', textAlign: 'center', minWidth: '120px' }}>
              <Code2 size={24} color="#4ade80" style={{ margin: '0 auto 6px auto' }} />
              <div style={{ color: '#f8fafc', fontWeight: 700, fontSize: '12px' }}>Coder Agent</div>
              <div style={{ color: '#4ade80', fontSize: '10px' }}>Compiling</div>
            </div>
            <ArrowRight size={20} color="#60a5fa" />
            <div style={{ padding: '16px', borderRadius: '12px', backgroundColor: '#1e293b', border: '2px solid #f59e0b', textAlign: 'center', minWidth: '120px' }}>
              <Layers size={24} color="#f59e0b" style={{ margin: '0 auto 6px auto' }} />
              <div style={{ color: '#f8fafc', fontWeight: 700, fontSize: '12px' }}>Video Renderer</div>
              <div style={{ color: '#facc15', fontSize: '10px' }}>Streaming</div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* OVERLAY UI CONTROLS & STATUS BADGES                                       */}
      {/* ========================================================================= */}

      {/* Top-Left Overlay: Red REC pill */}
      <div
        style={{
          position: 'absolute',
          top: '14px',
          left: '14px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 14px',
          borderRadius: '9999px',
          backgroundColor: 'rgba(15, 23, 42, 0.85)',
          border: '1px solid rgba(239, 68, 68, 0.4)',
          backdropFilter: 'blur(8px)',
          zIndex: 20,
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            backgroundColor: '#ef4444',
            boxShadow: isRecording ? '0 0 10px #ef4444' : 'none',
            animation: isRecording ? 'pulse 1.5s infinite' : 'none',
          }}
        />
        <span style={{ color: '#f8fafc', fontSize: '12px', fontWeight: 700, letterSpacing: '0.5px' }}>
          REC
        </span>
        <span style={{ color: '#fca5a5', fontSize: '12px', fontWeight: 600, fontFamily: 'monospace' }}>
          {recordingTimeFormatted}
        </span>
      </div>

      {/* Top-Center Overlay: AI Action Mode Switcher Tabs */}
      <div
        style={{
          position: 'absolute',
          top: '14px',
          left: '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          padding: '4px',
          borderRadius: '10px',
          backgroundColor: 'rgba(15, 23, 42, 0.85)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          backdropFilter: 'blur(8px)',
          zIndex: 20,
        }}
      >
        <button
          onClick={() => setScreenMode('host')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: screenMode === 'host' ? '#2563eb' : 'transparent',
            border: 'none',
            color: screenMode === 'host' ? '#ffffff' : '#94a3b8',
            fontSize: '11px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Sparkles size={12} /> AI Host
        </button>
        <button
          onClick={() => setScreenMode('code')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: screenMode === 'code' ? '#2563eb' : 'transparent',
            border: 'none',
            color: screenMode === 'code' ? '#ffffff' : '#94a3b8',
            fontSize: '11px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Code2 size={12} /> Code Studio
        </button>
        <button
          onClick={() => setScreenMode('terminal')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: screenMode === 'terminal' ? '#2563eb' : 'transparent',
            border: 'none',
            color: screenMode === 'terminal' ? '#ffffff' : '#94a3b8',
            fontSize: '11px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <TerminalIcon size={12} /> Terminal
        </button>
        <button
          onClick={() => setScreenMode('browser')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: screenMode === 'browser' ? '#2563eb' : 'transparent',
            border: 'none',
            color: screenMode === 'browser' ? '#ffffff' : '#94a3b8',
            fontSize: '11px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <Globe size={12} /> Browser
        </button>
        <button
          onClick={() => setScreenMode('swarm')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: screenMode === 'swarm' ? '#2563eb' : 'transparent',
            border: 'none',
            color: screenMode === 'swarm' ? '#ffffff' : '#94a3b8',
            fontSize: '11px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <GitBranch size={12} /> Swarm
        </button>
      </div>

      {/* Top-Right Overlay: Spec tags */}
      <div
        style={{
          position: 'absolute',
          top: '14px',
          right: '14px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          zIndex: 20,
        }}
      >
        <span
          style={{
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(8px)',
            color: '#e2e8f0',
            fontSize: '11px',
            fontWeight: 600,
          }}
        >
          {resolution.includes('4K') ? '4K' : '1080p'}
        </span>
        <span
          style={{
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(8px)',
            color: '#e2e8f0',
            fontSize: '11px',
            fontWeight: 600,
          }}
        >
          {fps} fps
        </span>
        <span
          style={{
            padding: '4px 10px',
            borderRadius: '6px',
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(8px)',
            color: '#e2e8f0',
            fontSize: '11px',
            fontWeight: 600,
          }}
        >
          16:9
        </span>
      </div>

      {/* Bottom-Left Overlay: AI Action status & live Voice Wave */}
      <div
        style={{
          position: 'absolute',
          bottom: '14px',
          left: '14px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          zIndex: 20,
        }}
      >
        {/* Active AI Agent pill */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 12px',
            borderRadius: '8px',
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            backdropFilter: 'blur(8px)',
            color: '#93c5fd',
            fontSize: '11px',
            fontWeight: 600,
          }}
        >
          <Bot size={13} color="#60a5fa" />
          <span>Agent: Orchestrator</span>
        </div>

        {/* Live Audio Visualizer Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '2px',
            padding: '5px 10px',
            borderRadius: '8px',
            backgroundColor: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <div style={{ width: '4px', height: '14px', borderRadius: '1px', background: '#22c55e' }} />
          <div style={{ width: '4px', height: '10px', borderRadius: '1px', background: '#22c55e' }} />
          <div style={{ width: '4px', height: '16px', borderRadius: '1px', background: '#22c55e' }} />
          <div style={{ width: '4px', height: '12px', borderRadius: '1px', background: '#eab308' }} />
          <div style={{ width: '4px', height: '8px', borderRadius: '1px', background: '#22c55e' }} />
          <div style={{ width: '4px', height: '14px', borderRadius: '1px', background: '#22c55e' }} />
          <div style={{ width: '4px', height: '6px', borderRadius: '1px', background: 'rgba(255, 255, 255, 0.2)' }} />
          <div style={{ width: '4px', height: '4px', borderRadius: '1px', background: 'rgba(255, 255, 255, 0.2)' }} />
        </div>
      </div>

      {/* Bottom-Right Overlay: Green LIVE AGENT Badge */}
      <div
        style={{
          position: 'absolute',
          bottom: '14px',
          right: '14px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 12px',
          borderRadius: '9999px',
          backgroundColor: 'rgba(15, 23, 42, 0.85)',
          border: '1px solid rgba(34, 197, 94, 0.4)',
          backdropFilter: 'blur(8px)',
          color: '#4ade80',
          fontSize: '11px',
          fontWeight: 700,
          letterSpacing: '0.8px',
          zIndex: 20,
        }}
      >
        <span
          style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: '#22c55e',
            boxShadow: '0 0 8px #22c55e',
          }}
        />
        LIVE AGENT
      </div>
    </div>
  );
};
