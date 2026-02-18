'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState(null);
  const [isMounted, setIsMounted] = useState(false);

  // Check if user is logged in on mount - FIX HYDRATION ERROR
  useEffect(() => {
    // Set mounted first to prevent hydration issues
    setIsMounted(true);
    
    // Only run on client side to avoid hydration mismatch
    const storedToken = localStorage.getItem('authToken');
    if (storedToken) {
      setToken(storedToken);
      // Try to get user info from stored data
      const storedUser = localStorage.getItem('user');
      if (storedUser) {
        try {
          setUser(JSON.parse(storedUser));
        } catch (e) {
          console.error('Failed to parse stored user:', e);
          localStorage.removeItem('user');
        }
      }
    }
  }, []);

  // Signup function
  const signup = async (username, email, password, confirmPassword) => {
    try {
      console.log('🔄 Starting signup request to http://localhost:5000/api/auth/signup');
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

      const response = await fetch('http://localhost:5000/api/auth/signup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          email,
          password,
          confirmPassword,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      console.log('📨 Signup response status:', response.status);

      if (!response.ok) {
        try {
          const errorData = await response.json();
          console.error('Server error response:', errorData);
          return { success: false, message: errorData.message || `Error: ${response.status}` };
        } catch (e) {
          return { success: false, message: `Server error: ${response.status} ${response.statusText}` };
        }
      }

      const data = await response.json();
      console.log('✅ Signup response received:', data);

      if (data.success) {
        setToken(data.token);
        setUser(data.user);
        localStorage.setItem('authToken', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        return { success: true, message: data.message };
      } else {
        return { success: false, message: data.message || 'Signup failed' };
      }
    } catch (error) {
      console.error('❌ Signup error:', error);
      
      if (error.name === 'AbortError') {
        return { success: false, message: 'Request timeout. Backend server not responding.' };
      }
      
      return { success: false, message: `Error during signup: ${error.message}. Make sure backend is running on http://localhost:5000` };
    }
  };

  // Login function
  const login = async (username, password) => {
    try {
      console.log('🔄 Starting login request to http://localhost:5000/api/auth/login');
      
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

      const response = await fetch('http://localhost:5000/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          password,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      console.log('📨 Login response status:', response.status);

      if (!response.ok) {
        try {
          const errorData = await response.json();
          console.error('Server error response:', errorData);
          return { success: false, message: errorData.message || `Error: ${response.status}` };
        } catch (e) {
          return { success: false, message: `Server error: ${response.status} ${response.statusText}` };
        }
      }

      const data = await response.json();
      console.log('✅ Login response received:', data);

      if (data.success) {
        setToken(data.token);
        setUser(data.user);
        localStorage.setItem('authToken', data.token);
        localStorage.setItem('user', JSON.stringify(data.user));
        return { success: true, message: data.message };
      } else {
        return { success: false, message: data.message || 'Login failed' };
      }
    } catch (error) {
      console.error('❌ Login error:', error);
      
      if (error.name === 'AbortError') {
        return { success: false, message: 'Request timeout. Backend server not responding.' };
      }
      
      return { success: false, message: `Error during login: ${error.message}. Make sure backend is running on http://localhost:5000` };
    }
  };

  // Logout function
  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, signup, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

// Hook to use auth context
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
