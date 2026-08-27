import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';
import './fixture.css';

document.body.dataset.retroTheme = 'windows-98';
createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>);
