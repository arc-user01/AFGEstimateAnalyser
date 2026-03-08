import React, { useState, useEffect, useRef } from 'react';
import { Upload, Send, FileText, Activity, ShieldCheck, AlertCircle, X, ChevronRight, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

const API_BASE = 'http://localhost:2357';

interface Message {
    id: string;
    type: 'user' | 'agent' | 'system';
    content: string;
    timestamp: string;
    data?: any;
}

interface Log {
    timestamp: string;
    level: string;
    message: string;
    task_id: string;
}

export default function App() {
    const [messages, setMessages] = useState<Message[]>([
        { id: '1', type: 'agent', content: 'Welcome to MSAF estimate Analyser. Please upload a TCO file (Required) and optionally Questionaries to begin.', timestamp: new Date().toLocaleTimeString() }
    ]);
    const [tcoFile, setTcoFile] = useState<File | null>(null);
    const [qFile, setQFile] = useState<File | null>(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [taskId, setTaskId] = useState<string | null>(null);
    const [logs, setLogs] = useState<Log[]>([]);
    const [showLogs, setShowLogs] = useState(false);

    const chatEndRef = useRef<HTMLDivElement>(null);
    const logEndRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    useEffect(() => {
        logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    // SSE Log Streaming
    useEffect(() => {
        if (taskId) {
            const eventSource = new EventSource(`${API_BASE}/stream/${taskId}`);
            eventSource.onmessage = (event) => {
                try {
                    const logData = JSON.parse(event.data);
                    setLogs(prev => [...prev, logData]);

                    // Close stream on completion signal
                    if (logData.message?.includes("--- [TASK_COMPLETE] ---")) {
                        console.log("Task complete signal received. Closing SSE.");
                        eventSource.close();
                    }
                } catch (e) {
                    // Keepalive or parse error
                }
            };
            eventSource.onerror = () => eventSource.close();
            return () => eventSource.close();
        }
    }, [taskId]);

    const handleProcess = async () => {
        if (!tcoFile) return;

        setIsProcessing(true);
        setLogs([]);
        setShowLogs(true);

        try {
            // 1. Upload TCO
            const tcoData = new FormData();
            tcoData.append('file', tcoFile);
            const tcoRes = await axios.post(`${API_BASE}/upload`, tcoData);

            // 2. Upload Q (if any)
            let qFilename = null;
            if (qFile) {
                const qData = new FormData();
                qData.append('file', qFile);
                const qRes = await axios.post(`${API_BASE}/upload`, qData);
                qFilename = qRes.data.filename;
            }

            // 3. Trigger Process
            const processRes = await axios.post(`${API_BASE}/process`, {
                rule_code: "r027", // Fixed for demo scenario
                tco_filename: tcoRes.data.filename,
                questionaries_filename: qFilename
            });

            setTaskId(processRes.data.task_id);
            setMessages(prev => [...prev, {
                id: Date.now().toString(),
                type: 'user',
                content: `Analying TCO: ${tcoFile.name} ${qFile ? ` & Questionaries: ${qFile.name}` : ''}`,
                timestamp: new Date().toLocaleTimeString()
            }]);

            // 4. Mimic "Fetch on Arrival" for result
            const pollResult = async () => {
                try {
                    const res = await axios.get(`${API_BASE}/result/${processRes.data.task_id}`);
                    if (res.data.status === 'success') {
                        setMessages(prev => [...prev, {
                            id: Date.now().toString(),
                            type: 'agent',
                            content: res.data.result,
                            timestamp: new Date().toLocaleTimeString()
                        }]);
                        setIsProcessing(false);
                    } else {
                        setTimeout(pollResult, 2000);
                    }
                } catch (e) {
                    setTimeout(pollResult, 5000);
                }
            };
            pollResult();

        } catch (e: any) {
            setMessages(prev => [...prev, { id: 'error', type: 'system', content: `Error: ${e.message}`, timestamp: new Date().toLocaleTimeString() }]);
            setIsProcessing(false);
        }
    };

    return (
        <div className="flex flex-col h-screen max-h-screen w-screen max-w-6xl mx-auto px-4 py-6 relative overflow-hidden">
            {/* Header */}
            <header className="flex items-center justify-between mb-8 px-6 py-4 glass-card rounded-3xl">
                <div className="flex items-center space-x-3">
                    <div className="w-10 h-10 bg-indigo-500 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-500/20">
                        <ShieldCheck className="text-white" size={24} />
                    </div>
                    <h1 className="text-2xl font-bold tracking-tight font-outfit">MSAF estimate Analyser</h1>
                </div>
                <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-widest text-zinc-500">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
                    <span>System Active</span>
                </div>
            </header>

            <div className="flex flex-1 gap-6 overflow-hidden min-h-0">
                {/* Main Chat Area */}
                <main className="flex-1 flex flex-col glass-card rounded-[2.5rem] overflow-hidden relative min-h-0">
                    <div className="flex-1 overflow-y-auto p-8 space-y-6">
                        <AnimatePresence>
                            {messages.map((m) => (
                                <motion.div
                                    key={m.id}
                                    initial={{ opacity: 0, y: 10, scale: 0.95 }}
                                    animate={{ opacity: 1, y: 0, scale: 1 }}
                                    className={m.type === 'user' ? 'chat-bubble-user' : 'chat-bubble-agent'}
                                >
                                    <div className="text-xs font-bold text-zinc-500 mb-2 uppercase tracking-tighter opacity-70">
                                        {m.type === 'agent' ? 'MSAF Internal Agent' : 'Product Owner'} • {m.timestamp}
                                    </div>
                                    <div className="whitespace-pre-wrap leading-relaxed text-[15px]">
                                        {m.content}
                                    </div>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                        <div ref={chatEndRef} />
                    </div>

                    {/* Input Area */}
                    <footer className="p-6 bg-white/5 border-t border-white/10">
                        <div className="flex items-center gap-4">
                            <div className="flex gap-2">
                                <FileButton label="TCO" file={tcoFile} setFile={setTcoFile} required />
                                <FileButton label="Q-Doc" file={qFile} setFile={setQFile} />
                            </div>
                            <button
                                disabled={!tcoFile || isProcessing}
                                onClick={handleProcess}
                                className="flex-1 py-4 px-6 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all rounded-2xl font-bold flex items-center justify-center space-x-2 shadow-xl shadow-indigo-600/20"
                            >
                                {isProcessing ? (
                                    <>
                                        <Loader2 className="animate-spin" size={20} />
                                        <span>Processing Estimate...</span>
                                    </>
                                ) : (
                                    <>
                                        <Send size={20} />
                                        <span>Run Analysis</span>
                                    </>
                                )}
                            </button>
                        </div>
                    </footer>
                </main>

                {/* Traceability Panel */}
                <AnimatePresence>
                    {showLogs && (
                        <motion.aside
                            initial={{ x: 300, opacity: 0 }}
                            animate={{ x: 0, opacity: 1 }}
                            exit={{ x: 300, opacity: 0 }}
                            className="w-96 glass-card rounded-[2.5rem] flex flex-col overflow-hidden shadow-2xl min-h-0 h-full"
                        >
                            <div className="p-6 border-b border-white/10 flex items-center justify-between">
                                <div className="flex items-center space-x-2">
                                    <Activity className="text-purple-400" size={18} />
                                    <h2 className="font-bold text-sm uppercase tracking-widest text-purple-100">Traceability Logs</h2>
                                </div>
                                <div className="flex items-center space-x-2">
                                    <button
                                        onClick={() => setLogs([])}
                                        className="p-1.5 hover:bg-white/10 rounded-lg text-zinc-500 hover:text-zinc-300 transition-colors"
                                        title="Clear Logs"
                                    >
                                        <X size={14} />
                                    </button>
                                    <button onClick={() => setShowLogs(false)} className="p-1.5 hover:bg-white/10 rounded-lg text-zinc-500 hover:text-white transition-colors">
                                        <ChevronRight size={18} />
                                    </button>
                                </div>
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-[11px] leading-tight custom-scrollbar">
                                {logs.length === 0 && (
                                    <div className="flex flex-col items-center justify-center h-full text-zinc-600 italic space-y-2">
                                        <Activity size={32} className="opacity-20 animate-pulse-slow" />
                                        <span>Waiting for logs...</span>
                                    </div>
                                )}
                                {logs.map((l, i) => (
                                    <div
                                        key={i}
                                        className={`p-2 rounded border break-all ${l.level === 'ERROR' ? 'bg-red-500/10 border-red-500/20 text-red-400' :
                                            l.level === 'SYSTEM' ? 'bg-purple-500/10 border-purple-500/20 text-purple-300' :
                                                'bg-white/5 border-white/5 text-zinc-400'
                                            }`}
                                    >
                                        <span className="text-zinc-600 font-bold">[{l.level}]</span> {l.message}
                                    </div>
                                ))}
                                <div ref={logEndRef} className="h-4" />
                            </div>
                            <div className="p-4 bg-purple-500/5 border-t border-white/5 text-center">
                                <div className="text-[10px] text-purple-300/50 uppercase font-black tracking-tighter">
                                    {isProcessing ? 'Agent Thinking...' : 'Ready for analysis'}
                                </div>
                            </div>
                        </motion.aside>
                    )}
                </AnimatePresence>
            </div>

            {/* Visual background element */}
            <div className="fixed top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/10 blur-[150px] -z-10 rounded-full"></div>
            <div className="fixed bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/10 blur-[150px] -z-10 rounded-full"></div>
        </div>
    );
}

function FileButton({ label, file, setFile, required }: { label: string, file: File | null, setFile: (f: File | null) => void, required?: boolean }) {
    const inputRef = useRef<HTMLInputElement>(null);

    return (
        <div className="relative group">
            <input
                type="file"
                className="hidden"
                ref={inputRef}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <button
                onClick={() => inputRef.current?.click()}
                className={`w-24 h-14 flex flex-col items-center justify-center rounded-2xl border transition-all ${file
                    ? 'bg-zinc-800 border-zinc-700 text-zinc-100'
                    : 'bg-white/5 border-white/10 text-zinc-500 hover:border-white/20 hover:text-zinc-300'
                    }`}
            >
                <span className="text-[10px] uppercase font-black mb-1">{label}</span>
                {file ? < ShieldCheck className="text-green-500" size={16} /> : <Upload size={16} />}
                {required && !file && <div className="absolute top-1 right-1 w-2 h-2 bg-indigo-500 rounded-full animate-ping"></div>}
            </button>
            {file && (
                <button
                    onClick={(e) => { e.stopPropagation(); setFile(null); }}
                    className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full flex items-center justify-center text-white scale-0 group-hover:scale-100 transition-transform"
                >
                    <X size={12} />
                </button>
            )}
        </div>
    );
}
