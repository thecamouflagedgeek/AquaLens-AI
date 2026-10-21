import React, { createContext, useContext, useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api, get, list } from './api';
const Auth = createContext(null);
export function AuthProvider({ children }) {
  const cache = useQueryClient();
  const session = useQuery({ queryKey: ['session'], queryFn: ({signal}) => get('/auth/me', undefined, signal), retry: false, staleTime: 60000 });
  useEffect(() => {
    const interceptor = api.interceptors.response.use(r => r, e => {
      if (e.response?.status === 401) cache.setQueryData(['session'], null);
      return Promise.reject(e);
    });
    return () => api.interceptors.response.eject(interceptor);
  }, [cache]);
  const login = async (credentials) => { await api.post('/auth/login', credentials); const user = await get('/auth/me'); cache.setQueryData(['session'], user); };
  const logout = async () => { await api.post('/auth/logout'); cache.clear(); cache.setQueryData(['session'], null); };
  return <Auth.Provider value={{user: session.data, pending: session.isPending, error: session.error, login, logout}}>{children}</Auth.Provider>;
}
export const useAuth = () => useContext(Auth);
const Monitoring = createContext(null);
export function MonitoringProvider({children}) {
  const [params, setParams] = useSearchParams();
  const [selection, setSelection] = useState(() => ({ station: params.get('station') || '', source: params.get('source') || '', from: params.get('from') || '', to: params.get('to') || '', observation: params.get('observation') || '' }));
  useEffect(() => { const next = Object.fromEntries(['station','source','from','to','observation'].map(k => [k, params.get(k) || ''])); if (next.station) setSelection(old => ({...old,...next})); }, [params]);
  const select = (patch) => { const next = {...selection,...patch}; setSelection(next); const url = new URLSearchParams(params); Object.entries(next).forEach(([k,v]) => v ? url.set(k,v) : url.delete(k)); setParams(url,{replace:true}); };
  const stations = useQuery({queryKey:['stations',selection.source],queryFn:({signal})=>get('/stations',{source_id:selection.source || undefined},signal)});
  const sources = useQuery({queryKey:['sources'],queryFn:({signal})=>get('/sources',undefined,signal)});
  return <Monitoring.Provider value={{...selection, select, stations, sources, stationRecord:list(stations.data).find(s=>String(s.id)===selection.station)}}>{children}</Monitoring.Provider>;
}
export const useMonitoring = () => useContext(Monitoring);
export function useResource(path, params) {
  return useQuery({queryKey:[path,params],queryFn:({signal})=>get(path,params,signal),enabled:!!path});
}
