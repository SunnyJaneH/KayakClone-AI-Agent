// src/components/ai/AiChatWidget.jsx
/**
 * AI Chat Widget Component
 * Floating chat button with notification badge
 * Receives real-time events via WebSocket
 */

import React, { useState, useEffect, useRef } from 'react';
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { sendChatMessage, createEventsWebSocket } from '../../api/aiService';
import { selectUser, selectIsAuthenticated } from '../../store/slices/authSlice';
import './ai.css';

const AiChatWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [pendingQuote, setPendingQuote] = useState(null);
  
  const messagesEndRef = useRef(null);
  const wsRef = useRef(null);
  const lastQuoteRef = useRef(null);
  const navigate = useNavigate();
  
  const user = useSelector(selectUser);
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const userId = user?.userId || 'guest_user';

  // Initialize WebSocket connection
  useEffect(() => {
    if (isAuthenticated && userId) {
      connectWebSocket();
    }
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isAuthenticated, userId]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const connectWebSocket = () => {
    try {
      wsRef.current = createEventsWebSocket(
        userId,
        handleWebSocketMessage,
        handleWebSocketError
      );
    } catch (err) {
      console.error('WebSocket connection failed:', err);
    }
  };

  const handleWebSocketMessage = (data) => {
    switch (data.event_type || data.type) {
      case 'price_alert':
      case 'inventory_alert':
      case 'deal_found':
      case 'watch_triggered':
        setNotifications(prev => [data, ...prev].slice(0, 10));
        setUnreadCount(prev => prev + 1);
        break;
      case 'pong':
        // Heartbeat response
        break;
      case 'connected':
        console.log('WebSocket connected');
        break;
      default:
        console.log('Unknown event:', data);
    }
  };

  const handleWebSocketError = (error) => {
    console.error('WebSocket error:', error);
    // Try to reconnect after 5 seconds
    setTimeout(() => {
      if (isAuthenticated) {
        connectWebSocket();
      }
    }, 5000);
  };

  // Handle booking redirect
  const handleBookingRedirect = (quoteData) => {
    const bookingData = {
      quote: quoteData,
      sessionId: sessionId,
      userId: userId
    };
    console.log('Navigating to booking with data:', bookingData);
    localStorage.setItem('aiBookingData', JSON.stringify(bookingData));
    
    setTimeout(() => {
      navigate('/booking/summary');
      setIsOpen(false);
    }, 500);
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || sending) return;

    const userMessage = input.trim();
    setInput('');
    setSending(true);

    // Add user message
    setMessages(prev => [...prev, {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString()
    }]);

    try {
      const response = await sendChatMessage(userMessage, userId, sessionId);
      
      // Update session ID
      if (response.session_id) {
        setSessionId(response.session_id);
      }
      
      // Check if this is a booking_confirmation from backend
      if (response.type === 'booking_confirmation') {
        console.log('Booking confirmation received:', response);
        
        // Add confirmation message
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: response.response || 'Great! Redirecting you to complete your booking...',
          timestamp: new Date().toISOString()
        }]);
        
        // Use lastQuoteRef for booking data
        if (lastQuoteRef.current) {
          handleBookingRedirect(lastQuoteRef.current);
        } else {
          // Fallback: create booking data from response
          handleBookingRedirect({
            response: response.response,
            bundles: response.bundles,
            booking: response.booking,
            timestamp: new Date().toISOString()
          });
        }
        
        setSending(false);
        return;
      }
      
      // Check if this is a quote response and save it
      if (response.type === 'quote' || response.response?.includes('Grand Total')) {
        const quoteData = {
          response: response.response,
          bundles: response.bundles,
          quote: response.quote,
          timestamp: new Date().toISOString()
        };
        lastQuoteRef.current = quoteData;
        setPendingQuote(quoteData);
        console.log('Quote saved:', quoteData);
      }

      // Add AI response
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.response,
        bundles: response.bundles,
        suggestions: response.suggestions,
        timestamp: new Date().toISOString()
      }]);
    } catch (err) {
      console.error('Chat error:', err);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        isError: true,
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setSending(false);
    }
  };

  const handleSuggestionClick = (suggestion) => {
    setInput(suggestion);
  };

  const handleNotificationClick = (notification) => {
    // Handle notification click - could navigate to relevant page
    console.log('Notification clicked:', notification);
    setShowNotifications(false);
  };

  const clearNotifications = () => {
    setNotifications([]);
    setUnreadCount(0);
    if (wsRef.current) {
      wsRef.current.clearUnread();
    }
  };

  const getNotificationIcon = (type) => {
    switch (type) {
      case 'price_alert':
        return 'bi-currency-dollar';
      case 'inventory_alert':
        return 'bi-box-seam';
      case 'deal_found':
        return 'bi-lightning';
      case 'watch_triggered':
        return 'bi-bell-fill';
      default:
        return 'bi-info-circle';
    }
  };

  return (
    <>
      {/* Floating Button */}
      <div className="ai-chat-widget">
        {/* Notification Bell */}
        <button 
          className="ai-widget-btn ai-notification-btn"
          onClick={() => setShowNotifications(!showNotifications)}
        >
          <i className="bi bi-bell"></i>
          {unreadCount > 0 && (
            <span className="ai-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
          )}
        </button>

        {/* Chat Button */}
        <button 
          className="ai-widget-btn ai-chat-btn"
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? (
            <i className="bi bi-x-lg"></i>
          ) : (
            <i className="bi bi-chat-dots-fill"></i>
          )}
        </button>
      </div>

      {/* Notifications Dropdown */}
      {showNotifications && (
        <div className="ai-notifications-dropdown">
          <div className="ai-notifications-header">
            <h4>Notifications</h4>
            {notifications.length > 0 && (
              <button onClick={clearNotifications}>Clear all</button>
            )}
          </div>
          <div className="ai-notifications-list">
            {notifications.length === 0 ? (
              <div className="ai-notifications-empty">
                <i className="bi bi-bell-slash"></i>
                <p>No notifications</p>
              </div>
            ) : (
              notifications.map((notif, idx) => (
                <div 
                  key={idx} 
                  className="ai-notification-item"
                  onClick={() => handleNotificationClick(notif)}
                >
                  <div className="ai-notification-icon">
                    <i className={`bi ${getNotificationIcon(notif.event_type)}`}></i>
                  </div>
                  <div className="ai-notification-content">
                    <strong>{notif.title}</strong>
                    <p>{notif.message}</p>
                    <small>{new Date(notif.timestamp).toLocaleTimeString()}</small>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Chat Window */}
      {isOpen && (
        <div className="ai-chat-window">
          {/* Chat Header */}
          <div className="ai-chat-header">
            <div className="ai-chat-title">
              <i className="bi bi-stars"></i>
              <span>AI Travel Assistant</span>
            </div>
            <button className="ai-chat-close" onClick={() => setIsOpen(false)}>
              <i className="bi bi-x"></i>
            </button>
          </div>

          {/* Messages */}
          <div className="ai-chat-messages">
            {messages.length === 0 && (
              <div className="ai-chat-welcome">
                <i className="bi bi-stars"></i>
                <h4>Hi! I'm your travel assistant</h4>
                <p>Ask me anything about flights, hotels, or travel planning.</p>
                <div className="ai-chat-suggestions">
                  <button onClick={() => handleSuggestionClick('Flights from Delhi to Mumbai, December 15-20')}>
                    Delhi to Mumbai
                  </button>
                  <button onClick={() => handleSuggestionClick('Hotels under $200 in Delhi')}>
                    Hotels in Delhi
                  </button>
                  <button onClick={() => handleSuggestionClick('Weekend getaway ideas')}>
                    Weekend getaway
                  </button>
                </div>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div 
                key={idx} 
                className={`ai-chat-message ai-chat-message--${msg.role} ${msg.isError ? 'ai-chat-message--error' : ''}`}
              >
                {msg.role === 'assistant' && (
                  <div className="ai-chat-avatar">
                    <i className="bi bi-stars"></i>
                  </div>
                )}
                <div className="ai-chat-bubble">
                  <p>{msg.content}</p>
                  
                  {/* Quick bundles preview */}
                  {msg.bundles?.length > 0 && (
                    <div className="ai-chat-bundles">
                      {msg.bundles.slice(0, 2).map((bundle, bidx) => (
                        <div key={bidx} className="ai-chat-bundle-mini">
                          <span>{bundle.name || bundle.destination}</span>
                          <span>${bundle.total_price?.toFixed(0)}</span>
                        </div>
                      ))}
                      <small>View details in AI Mode</small>
                    </div>
                  )}

                  {/* Suggestions */}
                  {msg.suggestions?.length > 0 && (
                    <div className="ai-chat-msg-suggestions">
                      {msg.suggestions.slice(0, 3).map((sug, sidx) => (
                        <button 
                          key={sidx}
                          onClick={() => handleSuggestionClick(sug)}
                        >
                          {sug}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {msg.role === 'user' && (
                  <div className="ai-chat-avatar ai-chat-avatar--user">
                    <i className="bi bi-person"></i>
                  </div>
                )}
              </div>
            ))}

            {sending && (
              <div className="ai-chat-message ai-chat-message--assistant">
                <div className="ai-chat-avatar">
                  <i className="bi bi-stars"></i>
                </div>
                <div className="ai-chat-bubble ai-chat-typing">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <form className="ai-chat-input" onSubmit={handleSend}>
            <input
              type="text"
              placeholder="Ask about travel..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={sending}
            />
            <button type="submit" disabled={sending || !input.trim()}>
              <i className="bi bi-send"></i>
            </button>
          </form>
        </div>
      )}
    </>
  );
};

export default AiChatWidget;
