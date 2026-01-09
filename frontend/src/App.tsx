import { useState, useEffect } from 'react'
import './App.css'
import { apiUrl } from './config'

interface Property {
  id: number
  name: string
  address: string | null
  city: string | null
  state: string | null
  zone: string | null
  phase: string | null
  priority: string | null
  asking_price: number | null
  unit_count: number | null
}

interface PipelineItem {
  id: number
  name: string
  address: string | null
  city: string | null
  state: string | null
  zone: string | null
  phase: string | null
  priority: string | null
  on_off_market: string | null
  asking_price: number | null
  unit_count: number | null
  date_added: string | null
}

function App() {
  const [properties, setProperties] = useState<PipelineItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [runningScreener, setRunningScreener] = useState<number | null>(null)
  const [screenerStatus, setScreenerStatus] = useState<string>('')

  useEffect(() => {
    fetchPipeline()
  }, [])

  const fetchPipeline = async () => {
    try {
      const response = await fetch(apiUrl('/api/pipeline'))
      if (!response.ok) throw new Error('Failed to fetch pipeline')
      const data = await response.json()
      setProperties(data)
      setLoading(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setLoading(false)
    }
  }

  const formatCurrency = (value: number | null) => {
    if (value === null) return '-'
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0
    }).format(value)
  }

  const getPriorityColor = (priority: string | null) => {
    switch (priority?.toLowerCase()) {
      case 'high': return 'bg-red-100 text-red-800'
      case 'medium': return 'bg-yellow-100 text-yellow-800'
      case 'low': return 'bg-green-100 text-green-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const runScreener = async (propertyId: number, propertyName: string) => {
    if (runningScreener) {
      alert('A screener is already running. Please wait.')
      return
    }

    setRunningScreener(propertyId)
    setScreenerStatus('Starting screener...')

    try {
      // Start the screener (runs in background)
      const response = await fetch(apiUrl(`/api/screener/${propertyId}/run`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to start screener')
      }

      const startResult = await response.json()
      setScreenerStatus(`Running... (Job #${startResult.run_id})`)

      // Poll for completion
      let attempts = 0
      const maxAttempts = 120 // 2 minutes max
      while (attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 2000)) // Wait 2 seconds

        const statusResponse = await fetch(apiUrl(`/api/screener/${propertyId}/status`))
        if (!statusResponse.ok) break

        const status = await statusResponse.json()
        setScreenerStatus(`${status.current_step} (${status.progress_percent}%)`)

        if (status.status === 'completed') {
          alert(`Screener completed for ${propertyName}!\n\nOutput: ${status.output_excel_path || 'See property folder'}`)
          break
        } else if (status.status === 'failed') {
          throw new Error(status.error_message || 'Screener failed')
        }

        attempts++
      }

      if (attempts >= maxAttempts) {
        alert('Screener is still running. Check back later.')
      }

    } catch (err) {
      setScreenerStatus('Error')
      alert(`Screener error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setRunningScreener(null)
      setScreenerStatus('')
    }
  }

  const getPhaseColor = (phase: string | null) => {
    switch (phase?.toLowerCase()) {
      case 'initial review': return 'bg-blue-100 text-blue-800'
      case 'screener': return 'bg-purple-100 text-purple-800'
      case 'loi': return 'bg-orange-100 text-orange-800'
      case 'under contract': return 'bg-green-100 text-green-800'
      case 'passed': return 'bg-gray-100 text-gray-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">RMP Pipeline</h1>
              <p className="text-gray-500 mt-1">Underwriting Deal Tracker</p>
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium"
            >
              + Add Property
            </button>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-gray-500 text-sm">Total Properties</p>
            <p className="text-2xl font-bold">{properties.length}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-gray-500 text-sm">In Review</p>
            <p className="text-2xl font-bold text-blue-600">
              {properties.filter(p => p.phase?.toLowerCase() === 'initial review').length}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-gray-500 text-sm">High Priority</p>
            <p className="text-2xl font-bold text-red-600">
              {properties.filter(p => p.priority?.toLowerCase() === 'high').length}
            </p>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <p className="text-gray-500 text-sm">Under LOI</p>
            <p className="text-2xl font-bold text-green-600">
              {properties.filter(p => p.phase?.toLowerCase() === 'loi').length}
            </p>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Property</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Location</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Zone</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Units</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Price</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Phase</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Priority</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-gray-500">
                    Loading...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-red-500">
                    Error: {error}
                  </td>
                </tr>
              ) : properties.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-gray-500">
                    No properties yet. Click "Add Property" to get started.
                  </td>
                </tr>
              ) : (
                properties.map((property) => (
                  <tr key={property.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900">{property.name}</div>
                      <div className="text-sm text-gray-500">{property.address}</div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {property.city}, {property.state}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {property.zone || 'NA'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {property.unit_count || '-'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {formatCurrency(property.asking_price)}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${getPhaseColor(property.phase)}`}>
                        {property.phase || 'New'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 text-xs font-medium rounded-full ${getPriorityColor(property.priority)}`}>
                        {property.priority || 'Medium'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <button
                        onClick={() => runScreener(property.id, property.name)}
                        disabled={runningScreener === property.id}
                        className={`mr-3 ${runningScreener === property.id
                          ? 'text-gray-400 cursor-wait'
                          : 'text-blue-600 hover:text-blue-800'
                        }`}
                      >
                        {runningScreener === property.id ? 'Running...' : 'Run Screener'}
                      </button>
                      <button className="text-gray-600 hover:text-gray-800">
                        Edit
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Property Modal */}
      {showAddModal && (
        <AddPropertyModal
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false)
            fetchPipeline()
          }}
        />
      )}
    </div>
  )
}

function AddPropertyModal({ onClose, onSuccess }: { onClose: () => void, onSuccess: () => void }) {
  const [formData, setFormData] = useState({
    name: '',
    address: '',
    city: '',
    state: '',
    zone: '',
    unit_count: '',
    asking_price: '',
  })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)

    try {
      const response = await fetch(apiUrl('/api/properties'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name,
          address: formData.address || null,
          city: formData.city || null,
          state: formData.state || null,
          zone: formData.zone || null,
          pipeline_status: {
            unit_count: formData.unit_count ? parseInt(formData.unit_count) : null,
            asking_price: formData.asking_price ? parseFloat(formData.asking_price) : null,
            phase: 'Initial Review',
            priority: 'Medium',
          }
        })
      })

      if (!response.ok) throw new Error('Failed to create property')
      onSuccess()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-xl font-bold mb-4">Add New Property</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Property Name *</label>
            <input
              type="text"
              required
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="e.g., Sunset Ridge Apartments"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Address</label>
            <input
              type="text"
              value={formData.address}
              onChange={(e) => setFormData({ ...formData, address: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="123 Main St"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">City</label>
              <input
                type="text"
                value={formData.city}
                onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">State</label>
              <input
                type="text"
                value={formData.state}
                onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="TX"
                maxLength={2}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Zone</label>
            <select
              value={formData.zone}
              onChange={(e) => setFormData({ ...formData, zone: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">NA (No Zone)</option>
              <option value="Zone 1">Zone 1 (CO, NM, WY)</option>
              <option value="Zone 2">Zone 2 (MN, MI, WI, AR)</option>
              <option value="Zone 3">Zone 3 (ID, MT, OR)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Units</label>
              <input
                type="number"
                value={formData.unit_count}
                onChange={(e) => setFormData({ ...formData, unit_count: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Asking Price</label>
              <input
                type="number"
                value={formData.asking_price}
                onChange={(e) => setFormData({ ...formData, asking_price: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="5000000"
              />
            </div>
          </div>

          <div className="flex justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Add Property'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default App
