const OpenAI = require('openai');
const { pool } = require('../config/database');

// DeepSeek Configuration
const openai = new OpenAI({
  baseURL: 'https://api.deepseek.com',
  apiKey: process.env.DEEPSEEK_API_KEY
});

// Store Python backend sessions in memory
const pythonSessions = {};

// System Prompt - Bot ko batana ke wo Business Analyst hai
const SYSTEM_PROMPT = `You are an expert Senior Business Analyst and Software Requirements Engineer. 
Your goal is to interview the user to gather requirements for their software project.
Ask clarifying questions one by one to understand:
1. Project Scope and Objectives
2. User Roles (Actors)
3. Functional Requirements
4. Non-functional Requirements (Performance, Security, etc.)
Keep your responses concise and professional. Do not generate the full SRS yet, just gather information.`;

// 1. Chat Process Function
exports.processChat = async (req, res) => {
  const { messages } = req.body; // Frontend se puri chat history aayegi
  const userId = req.user ? req.user.id : 'guest'; // Agar user logged in hai
  const lastUserMessage = messages[messages.length - 1].content;

  try {
    let aiResponse;
    let usedPythonBackend = false;

    // 1. Koshish karein Python Backend (SRS Generator) ko call karne ki
    try {
      let sessionId = pythonSessions[userId];
      let data;

      // Helper function to call Python API
      const callPython = async (endpoint, body) => {
        const response = await fetch(`http://127.0.0.1:8000/graph/${endpoint}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (!response.ok) throw new Error(`Python API Error: ${response.status}`);
        return await response.json();
      };

      if (!sessionId) {
        // New Session Start karein
        data = await callPython('start', { idea: lastUserMessage });
        pythonSessions[userId] = data.session_id;
      } else {
        // Existing Session ko aage barhayen
        try {
          data = await callPython('step', { session_id: sessionId, answer: lastUserMessage });
        } catch (err) {
          // Agar session expire ho gaya ho (404), to restart karein
          console.log("Session expired or not found, restarting...");
          data = await callPython('start', { idea: lastUserMessage });
          pythonSessions[userId] = data.session_id;
        }
      }

      // Python context se jawab nikalna
      const ctx = data.context || {};
      // Check karein ke context mein messages hain ya question
      if (ctx.messages && Array.isArray(ctx.messages) && ctx.messages.length > 0) {
        const lastMsg = ctx.messages[ctx.messages.length - 1];
        aiResponse = lastMsg.content || lastMsg.text || JSON.stringify(lastMsg);
      } else if (ctx.question) {
        aiResponse = ctx.question;
      } else {
        aiResponse = "I have processed your input. Please continue.";
      }
      usedPythonBackend = true;

    } catch (pythonError) {
      console.warn("⚠️ Python backend unavailable, falling back to DeepSeek Direct.", pythonError.message);
      
      // 2. Fallback: Agar Python backend band hai to direct DeepSeek use karein
      const completion = await openai.chat.completions.create({
        messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
        model: "deepseek-chat",
      });
      aiResponse = completion.choices[0].message.content;
    }

    // Agar user logged in hai to DB mein save karein
    if (req.user) {
      await pool.execute(
        'INSERT INTO chat_history (user_id, message, response) VALUES (?, ?, ?)', 
        [req.user.id, lastUserMessage, aiResponse]
      );
    }

    res.json({ 
      success: true, 
      content: aiResponse 
    });

  } catch (error) {
    console.error('Chat Processing Error:', error);
    res.status(500).json({ success: false, error: "Failed to process chat" });
  }
};

// 2. Get Chat History (Existing function)
exports.getHistory = async (req, res) => {
  try {
    const [rows] = await pool.execute(
      'SELECT message, response, created_at FROM chat_history WHERE user_id = ? ORDER BY created_at ASC',
      [req.user.id]
    );
    res.json({ success: true, data: { chats: rows } });
  } catch (error) {
    res.status(500).json({ success: false, error: error.message });
  }
};

// 3. Generate SRS Document
exports.generateSRS = async (req, res) => {
  const { messages } = req.body;

  const SRS_PROMPT = `Based on the conversation history provided, generate a comprehensive IEEE 830 Software Requirements Specification (SRS) document.
  
  Output Format: Markdown.
  
  Include these sections:
  1. Introduction (Purpose, Scope)
  2. Overall Description (User Characteristics, Assumptions)
  3. Functional Requirements (List detailed requirements)
  4. Non-functional Requirements (Security, Performance)
  5. System Models (Description of Use Cases)
  
  Make it professional and detailed.`;

  try {
    const completion = await openai.chat.completions.create({
      messages: [
        { role: "system", content: "You are a technical writer generating an SRS document." },
        ...messages,
        { role: "user", content: SRS_PROMPT }
      ],
      model: "deepseek-chat", // Ya deepseek-coder use karein agar better result chahiye
    });

    const srsContent = completion.choices[0].message.content;

    res.json({ success: true, srs: srsContent });

  } catch (error) {
    console.error('SRS Generation Error:', error);
    res.status(500).json({ success: false, error: "Failed to generate SRS" });
  }
};

// 4. Save Chat (Manual - agar zaroorat ho)
exports.saveChat = async (req, res) => {
  // Yeh ab processChat mein handle ho raha hai, lekin backward compatibility ke liye rakh sakte hain
  res.json({ success: true, message: "Chat saved automatically in processChat" });
};
