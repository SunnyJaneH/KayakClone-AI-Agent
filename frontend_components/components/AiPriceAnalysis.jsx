// src/components/ai/AiPriceAnalysis.jsx
/**
 * AI Price Analysis Component
 * Shows price verdict, history, and comparison
 * Implements "Decide with confidence" feature
 */

import React, { useState, useEffect } from 'react';
import { getPriceAnalysis, getBundleAnalysis } from '../../api/aiService';
import './ai.css';

const AiPriceAnalysis = ({ 
  listingType, 
  listingId, 
  bundleId,
  onClose,
  onBook 
}) => {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAnalysis();
  }, [listingType, listingId, bundleId]);

  const fetchAnalysis = async () => {
    try {
      setLoading(true);
      setError(null);
      
      let data;
      if (bundleId) {
        data = await getBundleAnalysis(bundleId);
      } else {
        data = await getPriceAnalysis(listingType, listingId);
      }
      setAnalysis(data);
    } catch (err) {
      console.error('Failed to fetch price analysis:', err);
      setError('Failed to load price analysis');
    } finally {
      setLoading(false);
    }
  };

  const getVerdictConfig = (verdict) => {
    switch (verdict?.toUpperCase()) {
      case 'EXCELLENT_DEAL':
        return { 
          color: '#22c55e', 
          bg: '#dcfce7', 
          icon: 'bi-trophy-fill',
          label: 'Excellent Deal',
          description: 'This is significantly below average - book now!'
        };
      case 'GREAT_DEAL':
        return { 
          color: '#3b82f6', 
          bg: '#dbeafe', 
          icon: 'bi-hand-thumbs-up-fill',
          label: 'Great Deal',
          description: 'Well below typical prices'
        };
      case 'GOOD_DEAL':
        return { 
          color: '#8b5cf6', 
          bg: '#ede9fe', 
          icon: 'bi-check-circle-fill',
          label: 'Good Deal',
          description: 'Slightly below average'
        };
      case 'FAIR_PRICE':
        return { 
          color: '#f59e0b', 
          bg: '#fef3c7', 
          icon: 'bi-dash-circle-fill',
          label: 'Fair Price',
          description: 'Around the typical price'
        };
      case 'ABOVE_AVERAGE':
        return { 
          color: '#ef4444', 
          bg: '#fef2f2', 
          icon: 'bi-exclamation-circle-fill',
          label: 'Above Average',
          description: 'Higher than usual - consider waiting'
        };
      default:
        return { 
          color: '#6b7280', 
          bg: '#f3f4f6', 
          icon: 'bi-question-circle-fill',
          label: 'Unknown',
          description: 'Unable to determine'
        };
    }
  };

  const formatPrice = (price) => {
    if (typeof price !== 'number') return '—';
    return `$${price.toFixed(0)}`;
  };

  const formatPercent = (percent) => {
    if (typeof percent !== 'number') return '—';
    const sign = percent >= 0 ? '+' : '';
    return `${sign}${percent.toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className="ai-modal-overlay">
        <div className="ai-modal ai-price-analysis-modal">
          <div className="ai-modal-loading">
            <div className="ai-spinner"></div>
            <p>Analyzing price...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="ai-modal-overlay">
        <div className="ai-modal ai-price-analysis-modal">
          <div className="ai-modal-header">
            <h2>Price Analysis</h2>
            <button className="ai-modal-close" onClick={onClose}>
              <i className="bi bi-x"></i>
            </button>
          </div>
          <div className="ai-modal-error">
            <i className="bi bi-exclamation-circle"></i>
            <p>{error}</p>
            <button onClick={fetchAnalysis}>Retry</button>
          </div>
        </div>
      </div>
    );
  }

  const verdictConfig = getVerdictConfig(analysis?.verdict);

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal ai-price-analysis-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="ai-modal-header">
          <h2><i className="bi bi-graph-up"></i> Price Analysis</h2>
          <button className="ai-modal-close" onClick={onClose}>
            <i className="bi bi-x"></i>
          </button>
        </div>

        {/* Verdict Section */}
        <div 
          className="ai-verdict-section"
          style={{ background: verdictConfig.bg }}
        >
          <div className="ai-verdict-icon" style={{ color: verdictConfig.color }}>
            <i className={`bi ${verdictConfig.icon}`}></i>
          </div>
          <div className="ai-verdict-content">
            <h3 style={{ color: verdictConfig.color }}>{verdictConfig.label}</h3>
            <p>{analysis?.verdict_explanation || verdictConfig.description}</p>
          </div>
          {analysis?.confidence && (
            <div className="ai-verdict-confidence">
              <span>{Math.round(analysis.confidence * 100)}%</span>
              <small>confidence</small>
            </div>
          )}
        </div>

        {/* Price Comparison */}
        <div className="ai-price-comparison">
          <div className="ai-price-item ai-price-current">
            <span className="ai-price-label">Current Price</span>
            <span className="ai-price-value">{formatPrice(analysis?.current_price)}</span>
          </div>
          <div className="ai-price-item">
            <span className="ai-price-label">30-Day Average</span>
            <span className="ai-price-value">{formatPrice(analysis?.avg_30d_price)}</span>
          </div>
          <div className="ai-price-item">
            <span className="ai-price-label">vs Average</span>
            <span 
              className="ai-price-value"
              style={{ 
                color: analysis?.price_vs_avg_percent < 0 ? '#22c55e' : '#ef4444' 
              }}
            >
              {formatPercent(analysis?.price_vs_avg_percent)}
            </span>
          </div>
        </div>

        {/* Price Range */}
        <div className="ai-price-range">
          <h4>30-Day Price Range</h4>
          <div className="ai-range-bar">
            <div className="ai-range-track">
              <div 
                className="ai-range-current"
                style={{
                  left: `${Math.max(0, Math.min(100, 
                    ((analysis?.current_price - analysis?.min_30d_price) / 
                    (analysis?.max_30d_price - analysis?.min_30d_price)) * 100
                  ))}%`
                }}
              >
                <div className="ai-range-marker"></div>
                <span>Now</span>
              </div>
            </div>
            <div className="ai-range-labels">
              <span>{formatPrice(analysis?.min_30d_price)}</span>
              <span>{formatPrice(analysis?.max_30d_price)}</span>
            </div>
          </div>
        </div>

        {/* Trend */}
        {analysis?.price_trend && (
          <div className="ai-price-trend">
            <h4>Price Trend</h4>
            <div className={`ai-trend-badge ai-trend-${analysis.price_trend}`}>
              <i className={`bi bi-arrow-${
                analysis.price_trend === 'rising' ? 'up' : 
                analysis.price_trend === 'falling' ? 'down' : 'right'
              }`}></i>
              {analysis.price_trend.charAt(0).toUpperCase() + analysis.price_trend.slice(1)}
            </div>
          </div>
        )}

        {/* Recommendation */}
        {analysis?.recommendation && (
          <div className="ai-recommendation">
            <h4><i className="bi bi-lightbulb"></i> Recommendation</h4>
            <p>{analysis.recommendation}</p>
            {analysis?.best_time_to_book && (
              <small>Best time to book: {analysis.best_time_to_book}</small>
            )}
          </div>
        )}

        {/* Similar Options */}
        {analysis?.similar_options?.length > 0 && (
          <div className="ai-similar-options">
            <h4>Similar Options</h4>
            <div className="ai-similar-list">
              {analysis.similar_options.slice(0, 3).map((option, idx) => (
                <div key={idx} className="ai-similar-item">
                  <span className="ai-similar-name">{option.name}</span>
                  <span className="ai-similar-price">{formatPrice(option.price)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="ai-modal-actions">
          <button className="ai-btn-secondary" onClick={onClose}>
            Keep Looking
          </button>
          <button className="ai-btn-primary" onClick={onBook}>
            <i className="bi bi-check-circle"></i>
            Book Now
          </button>
        </div>
      </div>
    </div>
  );
};

export default AiPriceAnalysis;
