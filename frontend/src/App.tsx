import { Routes, Route } from 'react-router-dom';
import { Nav } from './components/Nav';
import Dashboard from './pages/Dashboard';
import NewJob from './pages/NewJob';
import JobDetail from './pages/JobDetail';
import System from './pages/System';

export default function App() {
  return (
    <div className="min-h-full">
      <Nav />
      <main className="mx-auto max-w-[1200px] px-6 py-10">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewJob />} />
          <Route path="/jobs/:jobId" element={<JobDetail />} />
          <Route path="/system" element={<System />} />
        </Routes>
      </main>
    </div>
  );
}
