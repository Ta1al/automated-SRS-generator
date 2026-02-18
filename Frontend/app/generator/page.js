"use client";
import { useState, useEffect } from "react";
import { Send, Menu, Plus, MessageSquare, FileText, Download, User, LogOut } from "lucide-react";
import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";

function GeneratorPage() {
  const router = useRouter();
  const { user, logout, token } = useAuth();
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [history, setHistory] = useState([]);
  const [showUser, setShowUser] = useState(false);

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (!mobile) {
        setSidebarOpen(true);
      } else {
        setSidebarOpen(false);
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  
  useEffect(() => {
    if (token) {
      fetchHistory();
    }
  }, [token]);

  useEffect(() => {
    if (user) {
      const timer = setTimeout(() => setShowUser(true), 1000);
      return () => clearTimeout(timer);
    } else {
      setShowUser(false);
    }
  }, [user]);

  const fetchHistory = async () => {
    try {
      const res = await fetch('http://localhost:5000/api/chat/history', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.success) {
        setHistory(data.data.chats.map(chat => chat.message));
      }
    } catch (err) {
      console.error("Failed to fetch history", err);
    }
  };

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMessage = { text: input, sender: 'user', id: Date.now() };
    const updatedMessages = [...messages, userMessage];
    
    setMessages(updatedMessages);
    setInput("");
    setIsTyping(true);
    
    try {
      // Convert messages to API format (role/content)
      const apiMessages = updatedMessages.map(msg => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.text
      }));

      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: apiMessages }),
      });

      const data = await response.json();
      if (data.error) throw new Error(data.error);

      const aiMessage = {
        text: data.content,
        sender: 'ai', 
        id: Date.now() + 1 
      };
      setMessages(prev => [...prev, aiMessage]);

      if (token) {
        try {
          await fetch('http://localhost:5000/api/chat/save', {
            method: 'POST',
            headers: { 
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}` 
            },
            body: JSON.stringify({ message: userMessage.text, response: data.content })
          });
          fetchHistory();
        } catch (err) {
          console.error("Failed to save chat", err);
        }
      }
    } catch (error) {
      console.error("Chat Error:", error);
      setMessages(prev => [...prev, { 
        text: `Error: ${error.message || "Connection failed. Please check your API key and restart server."}`, 
        sender: 'ai', 
        id: Date.now() + 1 
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-900 text-white overflow-hidden font-sans">
      
      {/* Sidebar - ChatGPT Style */}
      <motion.aside 
        initial={{ width: 0 }}
        animate={{ width: isSidebarOpen ? 260 : 0 }}
        className="bg-black/50 border-r border-white/10 flex flex-col overflow-hidden md:relative absolute z-20 h-full md:h-auto"
      >
        <div className="p-4">
          <button className="flex items-center gap-2 w-full px-4 py-3 bg-white/5 hover:bg-white/10 rounded-lg border border-white/10 transition text-sm">
            <Plus className="w-4 h-4" />
            <span>New Project</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2">
          <div className="text-xs font-semibold text-gray-500 px-4 py-2">History</div>
          {history.map((item, idx) => (
            <button key={idx} className="flex items-center gap-3 w-full px-4 py-3 text-gray-300 hover:bg-white/5 rounded-lg text-sm transition overflow-hidden whitespace-nowrap">
              <MessageSquare className="w-4 h-4 shrink-0" />
              {item}
            </button>
          ))}
        </div>

        {user && showUser && (
          <div className="p-4 border-t border-white/10 space-y-2">
            <button className="flex items-center gap-3 w-full px-2 py-2 hover:bg-white/5 rounded-lg transition">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center">
                <User className="w-4 h-4 text-white" />
              </div>
              <div className="text-sm text-left">
                <div className="font-medium">{user.username || 'User'}</div>
                <div className="text-xs text-gray-400">Free Plan</div>
              </div>
            </button>
            <button 
              onClick={handleLogout}
              className="flex items-center gap-3 w-full px-2 py-2 text-red-400 hover:bg-red-500/20 rounded-lg transition text-sm"
            >
              <LogOut className="w-4 h-4" />
              Logout
            </button>
          </div>
        )}
      </motion.aside>

      <main className="flex-1 flex flex-col relative">
        {isSidebarOpen && isMobile && <div className="absolute inset-0 bg-black/50 z-10" onClick={() => setSidebarOpen(false)}></div>}
        {/* Header */}
        <header className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-gray-900/50 backdrop-blur">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(!isSidebarOpen)} className="p-2 hover:bg-white/10 rounded-lg text-gray-400">
              <Menu className="w-5 h-5" />
            </button>
            <span className="font-semibold text-gray-200">AI SRS Generator</span>
          </div>
          {/* Export Button - SRS FR-8, FR-9 [cite: 272, 276] */}
          <button className="p-2 hover:bg-white/10 rounded-lg text-gray-400" title="Export SRS">
            <Download className="w-5 h-5" />
          </button>
        </header>

        {/* Chat Content */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 scroll-smooth">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center space-y-6">
              <div className="w-16 h-16 bg-white/10 rounded-full flex items-center justify-center mb-4">
                <FileText className="w-8 h-8 text-blue-400" />
              </div>
              <h2 className="text-2xl font-bold">What project are we building today?</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-2xl w-full">
                <CardExample text="Create an SRS for a Food Delivery App." onClick={() => setInput("Create an SRS for a Food Delivery App.")} />
                <CardExample text="Build requirements for an IoT System." onClick={() => setInput("Build requirements for an IoT System.")} />
              </div>
            </div>
          ) : (
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((message) => (
                <motion.div 
                  key={message.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className={`flex gap-4 ${message.sender === 'user' ? 'justify-start' : ''}`}
                >
                  {message.sender === 'user' && (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-green-500 flex items-center justify-center shrink-0">
                      <User className="w-4 h-4 text-white" />
                    </div>
                  )}
                  {message.sender === 'ai' && (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shrink-0">
                      <span className="text-xs font-bold text-white">AI</span>
                    </div>
                  )}
                  <div className={`px-4 py-2 rounded-2xl max-w-[80%] ${
                    message.sender === 'user' 
                      ? 'bg-blue-600 rounded-tl-sm' 
                      : 'bg-white/5 rounded-tl-sm'
                  }`}>
                    {message.text}
                  </div>
                </motion.div>
              ))}
              {isTyping && (
                <motion.div 
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex gap-4"
                >
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center shrink-0">
                    <span className="text-xs font-bold text-white">AI</span>
                  </div>
                  <div className="bg-white/5 px-4 py-2 rounded-2xl rounded-tl-sm">
                    <div className="flex space-x-1">
                      <motion.div 
                        className="w-2 h-2 bg-gray-400 rounded-full"
                        animate={{ y: [0, -5, 0] }}
                        transition={{ duration: 0.8, repeat: Infinity }}
                      />
                      <motion.div 
                        className="w-2 h-2 bg-gray-400 rounded-full"
                        animate={{ y: [0, -5, 0] }}
                        transition={{ duration: 0.8, repeat: Infinity, delay: 0.2 }}
                      />
                      <motion.div 
                        className="w-2 h-2 bg-gray-400 rounded-full"
                        animate={{ y: [0, -5, 0] }}
                        transition={{ duration: 0.8, repeat: Infinity, delay: 0.4 }}
                      />
                    </div>
                  </div>
                </motion.div>
              )}
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-white/10 bg-gray-900">
          <div className="max-w-3xl mx-auto relative">
            <textarea
              className="w-full bg-white/5 border border-white/10 rounded-xl pl-4 pr-12 py-3 focus:outline-none focus:border-blue-500 resize-none text-gray-200"
              placeholder="Describe your project here..."
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            />
            <motion.button 
              className="absolute right-3 bottom-3 p-1.5 bg-blue-600 rounded-lg hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!input.trim() || isTyping}
              onClick={handleSend}
            >
              <Send className="w-4 h-4" />
            </motion.button>
          </div>
        </div>
      </main>
    </div>
  );
}

// Helper component
function CardExample({ text, onClick }) {
  return (
    <button 
      className="p-4 text-sm text-left bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition"
      onClick={onClick}
    >
      {text}
    </button>
  );
}

export default GeneratorPage;