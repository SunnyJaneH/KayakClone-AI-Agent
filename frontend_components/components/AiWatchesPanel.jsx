// src/components/ai/AiWatchesPanel.jsx
/**
 * AI Watches Panel Component
 * Displays user's price/inventory watches
 * Implements "Keep an eye on it" feature
 */

import React, { useState, useEffect } from 'react';
import { getWatches, deleteWatch, toggleWatch, createWatch } from '../../api/aiService';
import './ai.css';

const AiWatchesPanel = ({ userId, onClose, onWatchTriggered }) => {
  const [watches, setWatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Fetch watches on mount
  useEffect(() => {
    if (userId) {
      fetchWatches();
    }
  }, [userId]);

  const fetchWatches = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getWatches(userId);
      setWatches(data.watches || []);
    } catch (err) {
      console.error('Failed to fetch watches:', err);
      setError('Failed to load watches');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (watchId) => {
    if (!window.confirm('Remove this watch?')) return;
    
    try {
      await deleteWatch(watchId);
      setWatches(watches.filter(w => w.watch_id !== watchId));
    } catch (err) {
      console.error('Failed to delete watch:', err);
      alert('Failed to remove watch');
    }
  };

  const handleToggle = async (watchId, currentActive) => {
    try {
      await toggleWatch(watchId, !currentActive);
      setWatches(watches.map(w => 
        w.watch_id === watchId ? { ...w, active: !currentActive } : w
      ));
    } catch (err) {
      console.error('Failed to toggle watch:', err);
    }
  };

  const getWatchTypeIcon = (type) => {
    switch (type) {
      case 'price':
        return 'bi-currency-dollar';
      case 'inventory':
        return 'bi-box-seam';
      case 'both':
        return 'bi-bell';
      default:
        return 'bi-eye';
    }
  };

  const formatThreshold = (watch) => {
    const parts = [];
    if (watch.price_threshold) {
      parts.push(`Price < $${watch.price_threshold}`);
    }
    if (watch.inventory_threshold) {
      parts.push(`Inventory < ${watch.inventory_threshold}`);
    }
    return parts.join(' • ') || 'No threshold set';
  };

  if (loading) {
    return (
      <div className="ai-watches-panel">
        <div className="ai-watches-header">
          <h3><i className="bi bi-bell"></i> My Watches</h3>
          <button className="ai-close-btn" onClick={onClose}>
            <i className="bi bi-x"></i>
          </button>
        </div>
        <div className="ai-watches-loading">
          <div className="ai-spinner"></div>
          <p>Loading watches...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-watches-panel">
      {/* Header */}
      <div className="ai-watches-header">
        <h3><i className="bi bi-bell"></i> My Watches</h3>
        <div className="ai-watches-actions">
          <button 
            className="ai-add-watch-btn"
            onClick={() => setShowCreateForm(!showCreateForm)}
          >
            <i className="bi bi-plus"></i>
            Add Watch
          </button>
          <button className="ai-close-btn" onClick={onClose}>
            <i className="bi bi-x"></i>
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="ai-watches-error">
          <i className="bi bi-exclamation-circle"></i>
          {error}
          <button onClick={fetchWatches}>Retry</button>
        </div>
      )}

      {/* Create Form */}
      {showCreateForm && (
        <WatchCreateForm 
          userId={userId}
          onCreated={(newWatch) => {
            setWatches([newWatch, ...watches]);
            setShowCreateForm(false);
          }}
          onCancel={() => setShowCreateForm(false)}
        />
      )}

      {/* Watches List */}
      <div className="ai-watches-list">
        {watches.length === 0 ? (
          <div className="ai-watches-empty">
            <i className="bi bi-bell-slash"></i>
            <p>No active watches</p>
            <small>Create a watch to get notified when prices drop or inventory is low</small>
          </div>
        ) : (
          watches.map((watch) => (
            <div 
              key={watch.watch_id} 
              className={`ai-watch-item ${!watch.active ? 'ai-watch-item--paused' : ''}`}
            >
              <div className="ai-watch-icon">
                <i className={`bi ${getWatchTypeIcon(watch.watch_type)}`}></i>
              </div>
              
              <div className="ai-watch-info">
                <div className="ai-watch-name">
                  {watch.listing_name || `${watch.listing_type} ${watch.listing_id}`}
                </div>
                <div className="ai-watch-threshold">
                  {formatThreshold(watch)}
                </div>
                <div className="ai-watch-meta">
                  <span className={`ai-watch-status ${watch.active ? 'active' : 'paused'}`}>
                    {watch.active ? 'Active' : 'Paused'}
                  </span>
                  {watch.triggered_count > 0 && (
                    <span className="ai-watch-triggered">
                      Triggered {watch.triggered_count}x
                    </span>
                  )}
                </div>
              </div>

              <div className="ai-watch-actions">
                <button 
                  className="ai-watch-action-btn"
                  onClick={() => handleToggle(watch.watch_id, watch.active)}
                  title={watch.active ? 'Pause' : 'Resume'}
                >
                  <i className={`bi bi-${watch.active ? 'pause' : 'play'}`}></i>
                </button>
                <button 
                  className="ai-watch-action-btn ai-watch-action-btn--danger"
                  onClick={() => handleDelete(watch.watch_id)}
                  title="Delete"
                >
                  <i className="bi bi-trash"></i>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div className="ai-watches-footer">
        <small>
          <i className="bi bi-info-circle"></i>
          Watches notify you via the notification bell when conditions are met
        </small>
      </div>
    </div>
  );
};

// Watch Create Form Sub-component
const WatchCreateForm = ({ userId, onCreated, onCancel }) => {
  const [formData, setFormData] = useState({
    listing_type: 'flight',
    listing_id: '',
    listing_name: '',
    watch_type: 'price',
    price_threshold: '',
    inventory_threshold: ''
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.listing_id) {
      alert('Please enter a listing ID');
      return;
    }

    try {
      setSubmitting(true);
      const watchData = {
        user_id: userId,
        listing_type: formData.listing_type,
        listing_id: formData.listing_id,
        listing_name: formData.listing_name || `${formData.listing_type} ${formData.listing_id}`,
        watch_type: formData.watch_type,
        price_threshold: formData.price_threshold ? parseFloat(formData.price_threshold) : null,
        inventory_threshold: formData.inventory_threshold ? parseInt(formData.inventory_threshold) : null
      };
      
      const result = await createWatch(watchData);
      onCreated(result);
    } catch (err) {
      console.error('Failed to create watch:', err);
      alert('Failed to create watch');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="ai-watch-create-form" onSubmit={handleSubmit}>
      <div className="ai-form-row">
        <label>Type</label>
        <select 
          value={formData.listing_type}
          onChange={(e) => setFormData({ ...formData, listing_type: e.target.value })}
        >
          <option value="flight">Flight</option>
          <option value="hotel">Hotel</option>
          <option value="bundle">Bundle</option>
        </select>
      </div>

      <div className="ai-form-row">
        <label>Listing ID</label>
        <input
          type="text"
          placeholder="e.g., flight_123"
          value={formData.listing_id}
          onChange={(e) => setFormData({ ...formData, listing_id: e.target.value })}
          required
        />
      </div>

      <div className="ai-form-row">
        <label>Name (optional)</label>
        <input
          type="text"
          placeholder="e.g., SFO → MIA Flight"
          value={formData.listing_name}
          onChange={(e) => setFormData({ ...formData, listing_name: e.target.value })}
        />
      </div>

      <div className="ai-form-row">
        <label>Watch for</label>
        <select 
          value={formData.watch_type}
          onChange={(e) => setFormData({ ...formData, watch_type: e.target.value })}
        >
          <option value="price">Price drop</option>
          <option value="inventory">Low inventory</option>
          <option value="both">Both</option>
        </select>
      </div>

      {(formData.watch_type === 'price' || formData.watch_type === 'both') && (
        <div className="ai-form-row">
          <label>Price threshold ($)</label>
          <input
            type="number"
            placeholder="e.g., 500"
            value={formData.price_threshold}
            onChange={(e) => setFormData({ ...formData, price_threshold: e.target.value })}
          />
        </div>
      )}

      {(formData.watch_type === 'inventory' || formData.watch_type === 'both') && (
        <div className="ai-form-row">
          <label>Inventory threshold</label>
          <input
            type="number"
            placeholder="e.g., 5"
            value={formData.inventory_threshold}
            onChange={(e) => setFormData({ ...formData, inventory_threshold: e.target.value })}
          />
        </div>
      )}

      <div className="ai-form-actions">
        <button type="button" className="ai-btn-cancel" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="ai-btn-submit" disabled={submitting}>
          {submitting ? 'Creating...' : 'Create Watch'}
        </button>
      </div>
    </form>
  );
};

export default AiWatchesPanel;
