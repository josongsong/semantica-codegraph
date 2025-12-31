import React, { useState, useEffect, useCallback } from 'react';

export function UserProfile({ userId }: { userId: string }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchUser() {
      const response = await fetch(`/api/users/${userId}`);
      const data = await response.json();
      setUser(data);
      setLoading(false);
    }

    fetchUser();
  }, [userId]);

  const handleUpdate = useCallback((newName: string) => {
    if (user) {
      setUser({ ...user, name: newName });
    }
  }, [user]);

  if (loading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="user-profile">
      <h1>{user?.name}</h1>
      <button onClick={() => handleUpdate('New Name')}>
        Update Name
      </button>
    </div>
  );
}

// Custom hook
export function useCustomHook(initialValue: number) {
  const [value, setValue] = useState(initialValue);

  const increment = () => setValue(v => v + 1);
  const decrement = () => setValue(v => v - 1);

  return { value, increment, decrement };
}
