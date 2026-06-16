// src/components/ai/AiChangeHighlight.jsx
/**
 * AI Change Highlight Component
 * Shows what changed when user refines search
 * Implements "Refine without starting over" visual feedback
 */

import React from 'react';
import './ai.css';

const AiChangeHighlight = ({ changes = [] }) => {
  if (!changes || changes.length === 0) return null;

  // Group changes by type
  const improvements = changes.filter(c => c.is_improvement);
  const tradeoffs = changes.filter(c => !c.is_improvement);

  const getChangeIcon = (field) => {
    switch (field?.toLowerCase()) {
      case 'price':
      case 'total_price':
        return 'bi-currency-dollar';
      case 'deal_score':
      case 'score':
        return 'bi-graph-up-arrow';
      case 'availability':
        return 'bi-calendar-check';
      case 'rating':
        return 'bi-star';
      case 'stops':
        return 'bi-airplane';
      case 'amenities':
        return 'bi-list-check';
      default:
        return 'bi-arrow-right';
    }
  };

  const formatValue = (value, field) => {
    if (value === null || value === undefined) return '—';
    
    // Price formatting
    if (field?.toLowerCase().includes('price')) {
      return typeof value === 'number' ? `$${value.toFixed(0)}` : value;
    }
    
    // Score formatting
    if (field?.toLowerCase().includes('score')) {
      return `${value}/100`;
    }
    
    return String(value);
  };

  return (
    <div className="ai-change-highlight">
      <div className="ai-change-header">
        <i className="bi bi-arrow-repeat"></i>
        <span>Updated based on your preferences</span>
      </div>

      <div className="ai-changes-grid">
        {/* Improvements */}
        {improvements.length > 0 && (
          <div className="ai-changes-section ai-changes-section--positive">
            <h4 className="ai-changes-title">
              <i className="bi bi-check-circle-fill"></i>
              Improvements
            </h4>
            <ul className="ai-changes-list">
              {improvements.map((change, idx) => (
                <li key={idx} className="ai-change-item ai-change-item--positive">
                  <i className={`bi ${getChangeIcon(change.field)}`}></i>
                  <span className="ai-change-field">{change.field}:</span>
                  <span className="ai-change-values">
                    <span className="ai-change-old">
                      {formatValue(change.previous_value, change.field)}
                    </span>
                    <i className="bi bi-arrow-right"></i>
                    <span className="ai-change-new">
                      {formatValue(change.new_value, change.field)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Tradeoffs */}
        {tradeoffs.length > 0 && (
          <div className="ai-changes-section ai-changes-section--neutral">
            <h4 className="ai-changes-title">
              <i className="bi bi-info-circle-fill"></i>
              Tradeoffs
            </h4>
            <ul className="ai-changes-list">
              {tradeoffs.map((change, idx) => (
                <li key={idx} className="ai-change-item ai-change-item--neutral">
                  <i className={`bi ${getChangeIcon(change.field)}`}></i>
                  <span className="ai-change-field">{change.field}:</span>
                  <span className="ai-change-values">
                    <span className="ai-change-old">
                      {formatValue(change.previous_value, change.field)}
                    </span>
                    <i className="bi bi-arrow-right"></i>
                    <span className="ai-change-new">
                      {formatValue(change.new_value, change.field)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Summary */}
      <div className="ai-change-summary">
        {improvements.length > 0 && tradeoffs.length === 0 && (
          <span className="ai-summary-positive">
            <i className="bi bi-hand-thumbs-up"></i>
            All changes are improvements!
          </span>
        )}
        {improvements.length > 0 && tradeoffs.length > 0 && (
          <span className="ai-summary-mixed">
            <i className="bi bi-balance-scale"></i>
            {improvements.length} improvement{improvements.length !== 1 ? 's' : ''}, 
            {' '}{tradeoffs.length} tradeoff{tradeoffs.length !== 1 ? 's' : ''}
          </span>
        )}
        {improvements.length === 0 && tradeoffs.length > 0 && (
          <span className="ai-summary-neutral">
            <i className="bi bi-info-circle"></i>
            Results adjusted to match your new criteria
          </span>
        )}
      </div>
    </div>
  );
};

export default AiChangeHighlight;
