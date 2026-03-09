'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../context/AuthContext';

export const withAuth = (Component) => {
  return function ProtectedRoute(props) {
    const router = useRouter();
    const { token, loading } = useAuth();

    useEffect(() => {
      if (!loading && !token) {
        router.push('/login');
      }
    }, [token, loading, router]);

    if (loading) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
            <p className="text-gray-300">Loading...</p>
          </div>
        </div>
      );
    }

    if (!token) {
      return null;
    }

    return <Component {...props} />;
  };
};
