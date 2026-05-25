"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { StandaloneConfig } from "@/lib/config";

interface ConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (config: StandaloneConfig) => void;
  initialConfig?: StandaloneConfig;
}

export function ConfigDialog({
  open,
  onOpenChange,
  onSave,
  initialConfig,
}: ConfigDialogProps) {
  const [deploymentUrl, setDeploymentUrl] = useState(
    initialConfig?.deploymentUrl || ""
  );
  const [assistantId, setAssistantId] = useState(
    initialConfig?.assistantId || ""
  );
  const [langsmithApiKey, setLangsmithApiKey] = useState(
    initialConfig?.langsmithApiKey || ""
  );

  useEffect(() => {
    if (open && initialConfig) {
      setDeploymentUrl(initialConfig.deploymentUrl);
      setAssistantId(initialConfig.assistantId);
      setLangsmithApiKey(initialConfig.langsmithApiKey || "");
    }
  }, [open, initialConfig]);

  const handleSave = () => {
    if (!deploymentUrl || !assistantId) {
      alert("请填写所有必填项");
      return;
    }

    onSave({
      deploymentUrl,
      assistantId,
      langsmithApiKey: langsmithApiKey || undefined,
    });
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>配置</DialogTitle>
          <DialogDescription>
            配置你的 LangGraph 部署。这些配置会保存到浏览器的 local storage 中。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="deploymentUrl">Deployment URL</Label>
            <Input
              id="deploymentUrl"
              placeholder="https://<deployment-url>"
              value={deploymentUrl}
              onChange={(e) => setDeploymentUrl(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="assistantId">Assistant ID</Label>
            <Input
              id="assistantId"
              placeholder="<assistant-id>"
              value={assistantId}
              onChange={(e) => setAssistantId(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="langsmithApiKey">
              LangSmith API Key{" "}
              <span className="text-muted-foreground">(可选)</span>
            </Label>
            <Input
              id="langsmithApiKey"
              type="password"
              placeholder="lsv2_pt_..."
              value={langsmithApiKey}
              onChange={(e) => setLangsmithApiKey(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
