import { Link, Route, Routes } from 'react-router-dom'
import './App.css'
import AnnotationWorkspace from './pages/AnnotationWorkspace'
import DatasetImport from './pages/DatasetImport'
import ModelsPage from './pages/ModelsPage'
import ProjectCreate from './pages/ProjectCreate'
import ProjectDashboard from './pages/ProjectDashboard'
import ProjectList from './pages/ProjectList'
import PromptEditor from './pages/PromptEditor'
import TaxonomyEditor from './pages/TaxonomyEditor'

function App() {
  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          LabelForge
        </Link>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<ProjectList />} />
          <Route path="/projects/new" element={<ProjectCreate />} />
          <Route path="/projects/:projectId" element={<ProjectDashboard />} />
          <Route path="/projects/:projectId/taxonomy" element={<TaxonomyEditor />} />
          <Route path="/projects/:projectId/import" element={<DatasetImport />} />
          <Route path="/projects/:projectId/annotate" element={<AnnotationWorkspace />} />
          <Route path="/projects/:projectId/prompts" element={<PromptEditor />} />
          <Route path="/projects/:projectId/models" element={<ModelsPage />} />
        </Routes>
      </main>
    </>
  )
}

export default App
