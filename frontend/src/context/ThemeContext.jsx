/**
 * ThemeContext — global dark/light/system theme engine.
 * Applies 'dark' class to <html> and persists to localStorage & database profile settings.
 * Backward compatible with boolean darkMode and toggleDark queries.
 */
import { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const ThemeContext = createContext({
  theme: 'system',
  darkMode: false,
  setTheme: () => {},
  toggleTheme: () => {},
  toggleDark: () => {},
  setDarkMode: () => {}
});

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => {
    return localStorage.getItem('theme') || 'system';
  });

  const [darkMode, setDarkMode] = useState(false);

  // Sync theme selection when localStorage changes (e.g. login sync)
  useEffect(() => {
    const handleStorageChange = () => {
      const savedTheme = localStorage.getItem('theme');
      if (savedTheme && savedTheme !== theme) {
        setThemeState(savedTheme);
      }
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [theme]);

  // Compute active dark mode state and apply class to documentElement
  useEffect(() => {
    const updateTheme = () => {
      let isDark = false;
      if (theme === 'system') {
        isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      } else {
        isDark = theme === 'dark';
      }
      setDarkMode(isDark);
      
      const root = document.documentElement;
      if (isDark) {
        root.classList.add('dark');
        root.style.colorScheme = 'dark';
      } else {
        root.classList.remove('dark');
        root.style.colorScheme = 'light';
      }
    };

    updateTheme();
    localStorage.setItem('theme', theme);

    // Listen for system changes if system theme is selected
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      if (theme === 'system') {
        updateTheme();
      }
    };
    
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  // Expose setTheme to also save to backend if user is logged in
  const setTheme = async (newTheme) => {
    setThemeState(newTheme);
    localStorage.setItem('theme', newTheme);
    const token = localStorage.getItem('token');
    if (token) {
      try {
        await api.post('/auth/theme', { theme: newTheme });
      } catch (err) {
        console.error('Failed to save theme to backend database:', err);
      }
    }
  };

  const toggleTheme = () => {
    if (theme === 'light') setTheme('dark');
    else if (theme === 'dark') setTheme('system');
    else setTheme('light');
  };

  return (
    <ThemeContext.Provider value={{ 
      theme, 
      setTheme, 
      darkMode, 
      toggleTheme, 
      toggleDark: toggleTheme,
      setDarkMode: (val) => setTheme(val ? 'dark' : 'light') 
    }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
