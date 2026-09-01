import React from 'react';
import ReactDOM from 'react-dom/client';
import '@siemens/ix/dist/siemens-ix/siemens-ix.css';
import { IxApplicationContext } from '@siemens/ix-react';
import './index.css';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <IxApplicationContext>
      <App />
    </IxApplicationContext>
);
