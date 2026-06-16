// src/components/ai/AiQuoteModal.jsx
/**
 * AI Quote Modal Component
 * Shows complete pricing breakdown before booking
 * Implements "Book or hand off cleanly" feature
 */

import React, { useState, useEffect } from 'react';
import { generateQuote, refreshQuote, initiateBooking } from '../../api/aiService';
import AiPolicyInfo from './AiPolicyInfo';
import './ai.css';

const AiQuoteModal = ({ 
  bundle,
  userId,
  travelers = 1,
  onClose,
  onBookingComplete 
}) => {
  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showPolicies, setShowPolicies] = useState(false);
  const [booking, setBooking] = useState(false);

  useEffect(() => {
    if (bundle) {
      fetchQuote();
    }
  }, [bundle]);

  const fetchQuote = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const data = await generateQuote({
        bundle_id: bundle.bundle_id,
        user_id: userId,
        travelers,
        flight_id: bundle.flight?.flight_id,
        hotel_id: bundle.hotel?.hotel_id,
        check_in: bundle.hotel?.check_in,
        check_out: bundle.hotel?.check_out
      });
      
      setQuote(data);
    } catch (err) {
      console.error('Failed to generate quote:', err);
      setError('Failed to generate quote');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (!quote?.quote_id) return;
    
    try {
      setLoading(true);
      const data = await refreshQuote(quote.quote_id);
      setQuote(data);
    } catch (err) {
      console.error('Failed to refresh quote:', err);
      setError('Failed to refresh quote');
    } finally {
      setLoading(false);
    }
  };

  const handleBook = async () => {
    if (!quote?.quote_id) return;
    
    try {
      setBooking(true);
      const result = await initiateBooking(quote.quote_id);
      onBookingComplete?.(result);
    } catch (err) {
      console.error('Booking failed:', err);
      setError('Booking failed. Please try again.');
    } finally {
      setBooking(false);
    }
  };

  const formatPrice = (price) => {
    if (typeof price !== 'number') return '—';
    return `$${price.toFixed(2)}`;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  // Check if quote is still valid
  const isQuoteValid = () => {
    if (!quote?.quote_valid_until) return true;
    return new Date(quote.quote_valid_until) > new Date();
  };

  if (loading) {
    return (
      <div className="ai-modal-overlay">
        <div className="ai-modal ai-quote-modal">
          <div className="ai-modal-loading">
            <div className="ai-spinner"></div>
            <p>Generating your quote...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="ai-modal-overlay">
        <div className="ai-modal ai-quote-modal">
          <div className="ai-modal-header">
            <h2>Complete Quote</h2>
            <button className="ai-modal-close" onClick={onClose}>
              <i className="bi bi-x"></i>
            </button>
          </div>
          <div className="ai-modal-error">
            <i className="bi bi-exclamation-circle"></i>
            <p>{error}</p>
            <button onClick={fetchQuote}>Retry</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal ai-quote-modal ai-quote-modal--large" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="ai-modal-header">
          <h2><i className="bi bi-receipt"></i> Complete Quote</h2>
          <button className="ai-modal-close" onClick={onClose}>
            <i className="bi bi-x"></i>
          </button>
        </div>

        {/* Quote validity warning */}
        {!isQuoteValid() && (
          <div className="ai-quote-expired">
            <i className="bi bi-clock"></i>
            <span>This quote has expired</span>
            <button onClick={handleRefresh}>Refresh Quote</button>
          </div>
        )}

        <div className="ai-quote-content">
          {/* Flight Quote */}
          {quote?.flight_quote && (
            <div className="ai-quote-section">
              <h3><i className="bi bi-airplane"></i> Flight</h3>
              <div className="ai-quote-item-header">
                <span>{bundle?.flight?.airline || 'Flight'}</span>
                <span>{bundle?.origin} → {bundle?.destination}</span>
              </div>
              
              <div className="ai-quote-breakdown">
                <div className="ai-quote-line">
                  <span>Base fare ({travelers} traveler{travelers > 1 ? 's' : ''})</span>
                  <span>{formatPrice(quote.flight_quote.base_fare)}</span>
                </div>
                <div className="ai-quote-line">
                  <span>Taxes & fees</span>
                  <span>{formatPrice(quote.flight_quote.taxes)}</span>
                </div>
                {quote.flight_quote.carrier_fee > 0 && (
                  <div className="ai-quote-line">
                    <span>Carrier fee</span>
                    <span>{formatPrice(quote.flight_quote.carrier_fee)}</span>
                  </div>
                )}
                {quote.flight_quote.baggage_fee > 0 && (
                  <div className="ai-quote-line">
                    <span>Baggage</span>
                    <span>{formatPrice(quote.flight_quote.baggage_fee)}</span>
                  </div>
                )}
                <div className="ai-quote-line ai-quote-subtotal">
                  <span>Flight Subtotal</span>
                  <span>{formatPrice(quote.flight_quote.subtotal)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Hotel Quote */}
          {quote?.hotel_quote && (
            <div className="ai-quote-section">
              <h3><i className="bi bi-building"></i> Hotel</h3>
              <div className="ai-quote-item-header">
                <span>{bundle?.hotel?.name || 'Hotel'}</span>
                <span>{quote.hotel_quote.nights} night{quote.hotel_quote.nights > 1 ? 's' : ''}</span>
              </div>
              
              <div className="ai-quote-breakdown">
                <div className="ai-quote-line">
                  <span>Room rate ({formatPrice(quote.hotel_quote.rate_per_night)}/night × {quote.hotel_quote.nights})</span>
                  <span>{formatPrice(quote.hotel_quote.room_total)}</span>
                </div>
                {quote.hotel_quote.resort_fee > 0 && (
                  <div className="ai-quote-line">
                    <span>Resort fee</span>
                    <span>{formatPrice(quote.hotel_quote.resort_fee)}</span>
                  </div>
                )}
                <div className="ai-quote-line">
                  <span>Taxes</span>
                  <span>{formatPrice(quote.hotel_quote.taxes)}</span>
                </div>
                <div className="ai-quote-line ai-quote-subtotal">
                  <span>Hotel Subtotal</span>
                  <span>{formatPrice(quote.hotel_quote.subtotal)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Summary */}
          <div className="ai-quote-summary">
            <div className="ai-quote-line">
              <span>Subtotal</span>
              <span>{formatPrice(quote?.summary?.subtotal)}</span>
            </div>
            {quote?.summary?.bundle_discount > 0 && (
              <div className="ai-quote-line ai-quote-discount">
                <span><i className="bi bi-tag"></i> Bundle Discount</span>
                <span>-{formatPrice(quote.summary.bundle_discount)}</span>
              </div>
            )}
            <div className="ai-quote-line ai-quote-total">
              <span>Total</span>
              <span>{formatPrice(quote?.summary?.grand_total)}</span>
            </div>
          </div>

          {/* Cancellation Summary */}
          {quote?.cancellation_summary && (
            <div className="ai-quote-cancellation">
              <h4><i className="bi bi-calendar-x"></i> Cancellation Policy</h4>
              <p>{quote.cancellation_summary}</p>
              <button 
                className="ai-link-btn"
                onClick={() => setShowPolicies(true)}
              >
                View full policies
              </button>
            </div>
          )}

          {/* Important Notes */}
          {quote?.important_notes?.length > 0 && (
            <div className="ai-quote-notes">
              <h4><i className="bi bi-info-circle"></i> Important Notes</h4>
              <ul>
                {quote.important_notes.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Quote validity */}
          {quote?.quote_valid_until && isQuoteValid() && (
            <div className="ai-quote-validity">
              <i className="bi bi-clock"></i>
              Quote valid until {formatDate(quote.quote_valid_until)}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="ai-modal-actions">
          <button className="ai-btn-secondary" onClick={onClose}>
            Back to Results
          </button>
          <button 
            className="ai-btn-primary"
            onClick={handleBook}
            disabled={booking || !isQuoteValid()}
          >
            {booking ? (
              <>
                <div className="ai-spinner ai-spinner--small"></div>
                Processing...
              </>
            ) : (
              <>
                <i className="bi bi-lock"></i>
                Book Now - {formatPrice(quote?.summary?.grand_total)}
              </>
            )}
          </button>
        </div>

        {/* Terms */}
        <div className="ai-quote-terms">
          <small>
            By clicking "Book Now", you agree to the{' '}
            <a href={quote?.terms_url || '#'} target="_blank" rel="noopener noreferrer">
              terms and conditions
            </a>
          </small>
        </div>

        {/* Policy Modal */}
        {showPolicies && (
          <AiPolicyInfo
            flightId={bundle?.flight?.flight_id}
            hotelId={bundle?.hotel?.hotel_id}
            onClose={() => setShowPolicies(false)}
          />
        )}
      </div>
    </div>
  );
};

export default AiQuoteModal;
