import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

export function useLearningPerformance() {
  return useQuery({
    queryKey: ['learning-performance'],
    queryFn: async () => {
      const response = await api.getPerformance();
      return response.data;
    },
    refetchInterval: 30000,
    staleTime: 25000,
    retry: 2,
  });
}

export function useLearningSymbols() {
  return useQuery({
    queryKey: ['learning-symbols'],
    queryFn: async () => {
      const response = await api.getSymbolPerformance();
      return response.data;
    },
    refetchInterval: 30000,
    staleTime: 25000,
    retry: 2,
  });
}

export function useLearningAdjustments() {
  return useQuery({
    queryKey: ['learning-adjustments'],
    queryFn: async () => {
      const response = await api.getAdjustments();
      return response.data;
    },
    refetchInterval: 60000,
    staleTime: 50000,
    retry: 2,
  });
}

export function useLearningLog() {
  return useQuery({
    queryKey: ['learning-log'],
    queryFn: async () => {
      const response = await api.getLearningLog(30);
      return response.data;
    },
    refetchInterval: 60000,
    staleTime: 50000,
    retry: 2,
  });
}
