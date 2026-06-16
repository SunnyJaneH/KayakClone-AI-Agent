// src/components/ai/AiBundleCard.jsx
/**
 * AI Bundle Card Component
 * Displays flight+hotel bundle with:
 * - Why this (≤25 words)
 * - What to watch (≤12 words)
 * - Deal score, savings, tags
 */

import React, { useState } from 'react';
import './ai.css';

const AiBundleCard = ({
  bundle,
  rank = 1,
  onWatchClick,
  onAnalyzeClick,
  onQuoteClick,
  onBookClick
}) => {
  const [expanded, setExpanded] = useState(false);

  if (!bundle) return null;

  const {
    bundle_id,
    name,
    destination,
    origin,
    total_price,
    separate_booking_price,
    savings,
    savings_percent,
    deal_score,
    fit_score,
    flight,
    hotel,
    why_this,
    what_to_watch,
    tags = [],
    availability
  } = bundle;

  // Score badge color
  const getScoreColor = (score) => {
    if (score >= 80) return 'ai-score--excellent';
    if (score >= 70) return 'ai-score--great';
    if (score >= 60) return 'ai-score--good';
    return 'ai-score--fair';
  };

  // Format price
  const formatPrice = (price) => {
    if (typeof price !== 'number') return '—';
    return `$${price.toFixed(0)}`;
  };

  return (
    <div className={`ai-bundle-card ${expanded ? 'ai-bundle-card--expanded' : ''}`}>
      {/* Rank Badge */}
      <div className="ai-bundle-rank">
        {rank === 1 ? '🏆' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `#${rank}`}
      </div>

      {/* Main Content */}
      <div className="ai-bundle-main">
        {/* Header Row */}
        <div className="ai-bundle-header">
          <div className="ai-bundle-title">
            <h3>{name || `${origin} → ${destination}`}</h3>
            <div className="ai-bundle-tags">
              {tags.slice(0, 4).map((tag, idx) => (
                <span key={idx} className="ai-tag">{tag}</span>
              ))}
            </div>
          </div>
          
          <div className="ai-bundle-score-section">
            <div className={`ai-score-badge ${getScoreColor(deal_score)}`}>
              <span className="ai-score-value">{deal_score}</span>
              <span className="ai-score-label">Deal Score</span>
            </div>
          </div>
        </div>

        {/* Why This - ≤25 words */}
        <div className="ai-bundle-why">
          <i className="bi bi-lightbulb"></i>
          <span>{why_this || 'Great value bundle'}</span>
        </div>

        {/* What to Watch - ≤12 words */}
        {what_to_watch && (
          <div className="ai-bundle-watch">
            <i className="bi bi-exclamation-triangle"></i>
            <span>{what_to_watch}</span>
          </div>
        )}

        {/* Price Row */}
        <div className="ai-bundle-price-row">
          <div className="ai-bundle-price">
            <span className="ai-price-total">{formatPrice(total_price)}</span>
            <span className="ai-price-label">total</span>
          </div>
          
          {savings > 0 && (
            <div className="ai-bundle-savings">
              <span className="ai-savings-amount">Save {formatPrice(savings)}</span>
              <span className="ai-savings-percent">
                ({savings_percent?.toFixed(0) || Math.round((savings / separate_booking_price) * 100)}% off)
              </span>
            </div>
          )}

          {availability && availability < 5 && (
            <div className="ai-bundle-urgency">
              <i className="bi bi-fire"></i>
              Only {availability} left!
            </div>
          )}
        </div>

        {/* Expandable Details */}
        <button 
          className="ai-bundle-expand-btn"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Less details' : 'View details'}
          <i className={`bi bi-chevron-${expanded ? 'up' : 'down'}`}></i>
        </button>

        {expanded && (
          <div className="ai-bundle-details">
            {/* Flight Details */}
            {flight && (
              <div className="ai-detail-section">
                <h4><i className="bi bi-airplane"></i> Flight</h4>
                <div className="ai-detail-row">
                  <span>{flight.airline || 'Airline'}</span>
                  <span className="ai-detail-price">{formatPrice(flight.price)}</span>
                </div>
                <div className="ai-detail-meta">
                  {flight.stops === 0 ? 'Direct' : `${flight.stops} stop${flight.stops > 1 ? 's' : ''}`}
                  {flight.departure && ` • ${new Date(flight.departure).toLocaleDateString()}`}
                </div>
              </div>
            )}

            {/* Hotel Details */}
            {hotel && (
              <div className="ai-detail-section">
                <h4><i className="bi bi-building"></i> Hotel</h4>
                <div className="ai-detail-row">
                  <span>{hotel.name || 'Hotel'}</span>
                  <span className="ai-detail-price">
                    {formatPrice(hotel.price_per_night)}/night
                  </span>
                </div>
                <div className="ai-detail-meta">
                  {hotel.rating && `${hotel.rating}★`}
                  {hotel.nights && ` • ${hotel.nights} nights`}
                  {hotel.amenities?.length > 0 && ` • ${hotel.amenities.slice(0, 3).join(', ')}`}
                </div>
              </div>
            )}

            {/* Fit Score if available */}
            {fit_score && (
              <div className="ai-fit-score">
                <span>Fit Score: {fit_score}/100</span>
                <small>Based on your preferences</small>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="ai-bundle-actions">
        <button 
          className="ai-action-btn ai-action-btn--secondary"
          onClick={onWatchClick}
          title="Watch price"
        >
          <i className="bi bi-bell"></i>
          Watch
        </button>
        
        <button 
          className="ai-action-btn ai-action-btn--secondary"
          onClick={onAnalyzeClick}
          title="Analyze price"
        >
          <i className="bi bi-graph-up"></i>
          Analyze
        </button>
        
        <button 
          className="ai-action-btn ai-action-btn--secondary"
          onClick={onQuoteClick}
          title="Get full quote"
        >
          <i className="bi bi-receipt"></i>
          Quote
        </button>
        
        <button 
          className="ai-action-btn ai-action-btn--primary"
          onClick={onBookClick}
        >
          <i className="bi bi-check-circle"></i>
          Book
        </button>
      </div>
    </div>
  );
};

export default AiBundleCard;
