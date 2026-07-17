import { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState(null)

  useEffect(() => {
    fetchJobs()
  }, [])

  const fetchJobs = async () => {
    try {
      const response = await fetch('http://localhost:8000/jobs')
      if (!response.ok) {
        throw new Error('Failed to fetch jobs')
      }
      const data = await response.json()
      setJobs(data)
    } catch (error) {
      setApiError(error.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
        <p className="mt-4 text-gray-600">Loading jobs...</p>
      </div>
    )
  }

  if (apiError) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center py-12">
        <h1 className="text-2xl font-bold text-red-600 mb-4">Error</h1>
        <p className="text-gray-600">{apiError}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-6 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <div className="h-10 w-10 bg-indigo-600 rounded-md flex items-center justify-center">
                  <span className="text-white text-xl">🌍</span>
                </div>
              </div>
              <div className="hidden md:block">
                <div className="ml-10 flex items-baseline space-x-4">
                  <a href="#" className="text-gray-900 hover:bg-gray-50 px-3 py-2 rounded-md text-sm font-medium">Dashboard</a>
                  <a href="#" className="text-gray-700 hover:bg-gray-50 px-3 py-2 rounded-md text-sm font-medium">Jobs</a>
                  <a href="#" className="text-indigo-600 hover:bg-gray-50 px-3 py-2 rounded-md text-sm font-medium">About</a>
                </div>
              </div>
            </div>
            <div className="hidden md:block">
              <div className="ml-4 flex items-center md:ml-4 space-x-4">
                <button
                  className="px-3 py-2 bg-white text-sm font-medium text-gray-900 shadow-sm hover:bg-gray-50 rounded-md"
                >
                  Sign in
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main>
        <div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
          <div className="px-4 py-6 sm:px-0">
            <div className="border-4 border-dashed border-gray-200 rounded-lg h-96 flex items-center justify-center mb-6">
              <div className="text-center">
                <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 10l7.393 9.242a1 1 0 001.423-.01L22 12l7.175 9.028a1 1 0 001.416-.02L38 10a1 1 0 001.045-.87l-3-4a1 1 0 00-1.33-.15l-3.61 4.513a1 1 0 01-1.437-.001L20 13l-6.32 7.935a1 1 0 01-1.423-.01l-3-4a1 1 0 00-1.045.87z"></path>
                </svg>
                <h2 className="mt-4 text-lg font-medium text-gray-900">No jobs yet</h2>
                <p className="mt-2 max-w-sm text-center text-sm text-gray-500">
                  Upload an OSM file to start a conversion job
                </p>
                <button
                  className="mt-4 px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
                >
                  Upload OSM File
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App