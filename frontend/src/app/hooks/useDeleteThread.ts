"use client";

import { useCallback, useState } from "react";
import { useClient } from "@/providers/ClientProvider";

export function useDeleteThread() {
  const client = useClient();
  const [isDeleting, setIsDeleting] = useState(false);

  const deleteThread = useCallback(
    async (threadId: string) => {
      setIsDeleting(true);
      try {
        await client.threads.delete(threadId);
      } finally {
        setIsDeleting(false);
      }
    },
    [client],
  );

  return { deleteThread, isDeleting };
}
