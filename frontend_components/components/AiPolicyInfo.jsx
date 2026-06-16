// src/components/ai/AiPolicyInfo.jsx
/**
 * AI Policy Info Component
 * Shows cancellation, change, and other policies
 * Supports asking policy questions via AI
 */

import React, { useState, useEffect } from 'react';
import { getListingPolicies, sendChatMessage } from '../../api/aiService';
import './ai.css';

const AiPolicyInfo = ({ 
  flightId, 
  hotelId, 
  bundleId,
  onClose 
}) => {
  const [flightPolicies, setFlightPolicies] = useState(null);
  const [hotelPolicies, setHotelPolicies] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    fetchPolicies();
  }, [flightId, hotelId]);

  const fetchPolicies = async () => {
    try {
      setLoading(true);
      setError(null);

      const promises = [];
      
      if (flightId) {
        promises.push(
          getListingPolicies('flight', flightId)
            .then(data => setFlightPolicies(data))
            .catch(() => setFlightPolicies(null))
        );
      }
      
      if (hotelId) {
        promises.push(
          getListingPolicies('hotel', hotelId)
            .then(data => setHotelPolicies(data))
            .catch(() => setHotelPolicies(null))
        );
      }

      await Promise.all(promises);
    } catch (err) {
      console.error('Failed to fetch policies:', err);
      setError('Failed to load policies');
    } finally {
      setLoading(false);
    }
  };

  const handleAskQuestion = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    try {
      setAsking(true);
      setAnswer(null);
      
      const response = await sendChatMessage(
        `Policy question about my booking: ${question}`,
        'policy_user',
        null
      );
      
      setAnswer(response.response);
    } catch (err) {
      console.error('Failed to get answer:', err);
      setAnswer('Sorry, I couldn\'t find an answer to that question.');
    } finally {
      setAsking(false);
    }
  };

  const commonQuestions = [
    'Can I cancel for free?',
    'What happens if I miss my flight?',
    'Is my booking refundable?',
    'Can I change my dates?',
    'Are pets allowed?'
  ];

  if (loading) {
    return (
      <div className="ai-modal-overlay">
        <div className="ai-modal ai-policy-modal">
          <div className="ai-modal-loading">
            <div className="ai-spinner"></div>
            <p>Loading policies...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal ai-policy-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="ai-modal-header">
          <h2><i className="bi bi-file-text"></i> Policies & Info</h2>
          <button className="ai-modal-close" onClick={onClose}>
            <i className="bi bi-x"></i>
          </button>
        </div>

        <div className="ai-policy-content">
          {/* Flight Policies */}
          {flightPolicies && (
            <div className="ai-policy-section">
              <h3><i className="bi bi-airplane"></i> Flight Policies</h3>
              
              <div className="ai-policy-item">
                <h4>Cancellation</h4>
                <p>
                  {flightPolicies.cancellation?.refundable 
                    ? `Refundable - ${flightPolicies.cancellation.refund_percent || 100}% refund`
                    : 'Non-refundable'}
                </p>
                {flightPolicies.cancellation?.deadline && (
                  <small>
                    Must cancel by {new Date(flightPolicies.cancellation.deadline).toLocaleDateString()}
                  </small>
                )}
              </div>

              <div className="ai-policy-item">
                <h4>Changes</h4>
                <p>
                  {flightPolicies.changes?.allowed 
                    ? `Changes allowed - $${flightPolicies.changes.fee || 0} fee`
                    : 'No changes allowed'}
                </p>
              </div>

              <div className="ai-policy-item">
                <h4>Baggage</h4>
                <p>
                  Carry-on: {flightPolicies.baggage?.carry_on || 'Included'}
                  <br />
                  Checked: {flightPolicies.baggage?.checked || 'Fee applies'}
                </p>
              </div>
            </div>
          )}

          {/* Hotel Policies */}
          {hotelPolicies && (
            <div className="ai-policy-section">
              <h3><i className="bi bi-building"></i> Hotel Policies</h3>
              
              <div className="ai-policy-item">
                <h4>Cancellation</h4>
                <p>
                  {hotelPolicies.cancellation?.free_cancellation 
                    ? 'Free cancellation available'
                    : 'Non-refundable'}
                </p>
                {hotelPolicies.cancellation?.deadline && (
                  <small>
                    Free cancel until {new Date(hotelPolicies.cancellation.deadline).toLocaleDateString()}
                  </small>
                )}
              </div>

              <div className="ai-policy-item">
                <h4>Check-in / Check-out</h4>
                <p>
                  Check-in: {hotelPolicies.check_in_time || '3:00 PM'}
                  <br />
                  Check-out: {hotelPolicies.check_out_time || '11:00 AM'}
                </p>
              </div>

              {hotelPolicies.pets && (
                <div className="ai-policy-item">
                  <h4>Pets</h4>
                  <p>
                    {hotelPolicies.pets.allowed 
                      ? `Pets allowed - $${hotelPolicies.pets.fee || 0}/night fee`
                      : 'No pets allowed'}
                  </p>
                </div>
              )}

              {hotelPolicies.parking && (
                <div className="ai-policy-item">
                  <h4>Parking</h4>
                  <p>
                    {hotelPolicies.parking.available 
                      ? `Available - ${hotelPolicies.parking.free ? 'Free' : `$${hotelPolicies.parking.fee}/day`}`
                      : 'Not available on-site'}
                  </p>
                </div>
              )}

              {hotelPolicies.amenities?.length > 0 && (
                <div className="ai-policy-item">
                  <h4>Amenities</h4>
                  <div className="ai-amenities-list">
                    {hotelPolicies.amenities.map((amenity, idx) => (
                      <span key={idx} className="ai-amenity-tag">
                        {amenity}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* No policies found */}
          {!flightPolicies && !hotelPolicies && (
            <div className="ai-policy-empty">
              <i className="bi bi-info-circle"></i>
              <p>No specific policies available for this selection.</p>
            </div>
          )}

          {/* Ask AI Section */}
          <div className="ai-policy-ask">
            <h3><i className="bi bi-chat-dots"></i> Have a Question?</h3>
            
            <div className="ai-quick-questions">
              {commonQuestions.map((q, idx) => (
                <button
                  key={idx}
                  className="ai-quick-q-btn"
                  onClick={() => {
                    setQuestion(q);
                  }}
                >
                  {q}
                </button>
              ))}
            </div>

            <form className="ai-ask-form" onSubmit={handleAskQuestion}>
              <input
                type="text"
                placeholder="Ask about policies, amenities, or restrictions..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <button type="submit" disabled={asking || !question.trim()}>
                {asking ? <div className="ai-spinner ai-spinner--small"></div> : <i className="bi bi-send"></i>}
              </button>
            </form>

            {answer && (
              <div className="ai-ask-answer">
                <i className="bi bi-robot"></i>
                <p>{answer}</p>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="ai-modal-actions">
          <button className="ai-btn-primary" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
};

export default AiPolicyInfo;
