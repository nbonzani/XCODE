import React from 'react'
import ReactDOM from 'react-dom/client'
import { init } from '@noriginmedia/norigin-spatial-navigation'
import App from './App.jsx'
import './styles/global.css'
import './styles/focus.css'

init({
  debug: false,
  visualDebug: false,
})

document.addEventListener('DOMContentLoaded', function() {
  var rootElement = document.getElementById('root')
  if (rootElement) {
    ReactDOM.createRoot(rootElement).render(
      React.createElement(App)
    )
  }
})
