"use client";

import { Button } from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Music4, Trash2, UploadCloud, Waves } from "lucide-react";
import { useState } from "react";

import { apiRequest } from "@/lib/client-api";

type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

type Campaign = {
  id: number;
  name: string;
  status: string;
  audio: {
    id: number;
    original_name: string;
    file_url: string;
  } | null;
};

type AudioResponse = {
  audio: {
    id: number;
    original_name: string;
    file_url: string;
    file_size: number;
    mime_type: string;
  } | null;
};

export function CampaignAudioPageClient() {
  const queryClient = useQueryClient();
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(
    null,
  );
  const [notice, setNotice] = useState<string | null>(null);

  const campaignsQuery = useQuery({
    queryKey: ["audio-campaigns"],
    queryFn: () =>
      apiRequest<PaginatedResponse<Campaign>>(
        "/api/backend/campaigns/?page_size=200",
      ),
  });

  const activeCampaignId =
    selectedCampaignId ?? campaignsQuery.data?.results[0]?.id ?? null;

  const audioQuery = useQuery({
    queryKey: ["campaign-audio", activeCampaignId],
    enabled: Boolean(activeCampaignId),
    queryFn: () =>
      apiRequest<AudioResponse>(
        `/api/backend/campaigns/${activeCampaignId}/audio/`,
      ),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      if (!activeCampaignId) {
        throw new Error("Select a campaign first.");
      }

      const formData = new FormData();
      formData.append("audio_file", file);

      return apiRequest(`/api/backend/campaigns/${activeCampaignId}/audio/`, {
        method: "POST",
        body: formData,
      });
    },
    onSuccess: () => {
      setNotice("Audio uploaded.");
      queryClient.invalidateQueries({
        queryKey: ["campaign-audio", activeCampaignId],
      });
      queryClient.invalidateQueries({ queryKey: ["audio-campaigns"] });
    },
    onError: (error) => {
      setNotice(
        error instanceof Error
          ? error.message
          : "Unable to upload the audio file.",
      );
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!activeCampaignId) {
        throw new Error("Select a campaign first.");
      }

      return apiRequest(`/api/backend/campaigns/${activeCampaignId}/audio/`, {
        method: "DELETE",
      });
    },
    onSuccess: () => {
      setNotice("Audio removed.");
      queryClient.invalidateQueries({
        queryKey: ["campaign-audio", activeCampaignId],
      });
      queryClient.invalidateQueries({ queryKey: ["audio-campaigns"] });
    },
  });

  const selectedCampaign = campaignsQuery.data?.results.find(
    (campaign) => campaign.id === activeCampaignId,
  );

  return (
    <div className="space-y-6">
      <div>
        <p className="section-heading">Voice assets</p>
        <h2 className="mt-2 text-3xl font-semibold text-slate-950">
          Campaign audio management
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-600">
          Upload a .wav or .mp3 file for each campaign, preview the file before
          calls go out, and remove it if the wrong recording was attached.
        </p>
      </div>

      {notice ? (
        <div className="rounded-2xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-900">
          {notice}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <section className="rounded-[1.6rem] border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-3">
            <Music4 className="size-5 text-teal-700" />
            <div>
              <h3 className="text-lg font-semibold text-slate-950">
                Campaign list
              </h3>
              <p className="text-sm text-slate-600">
                Select which campaign should receive a pre-recorded prompt.
              </p>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {campaignsQuery.isLoading ? (
              <>
                <div className="skeleton-block h-16" />
                <div className="skeleton-block h-16" />
                <div className="skeleton-block h-16" />
              </>
            ) : (
              campaignsQuery.data?.results.map((campaign) => (
                <button
                  key={campaign.id}
                  className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                    activeCampaignId === campaign.id
                      ? "border-teal-400 bg-teal-50"
                      : "border-slate-200 bg-slate-50 hover:border-teal-200"
                  }`}
                  onClick={() => setSelectedCampaignId(campaign.id)}
                  type="button"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-slate-900">
                        {campaign.name}
                      </p>
                      <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">
                        {campaign.status}
                      </p>
                    </div>
                    <span className="text-xs text-slate-500">
                      {campaign.audio ? "Audio ready" : "No audio"}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="rounded-[1.6rem] border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-3">
            <Waves className="size-5 text-amber-700" />
            <div>
              <h3 className="text-lg font-semibold text-slate-950">
                {selectedCampaign ? selectedCampaign.name : "Select a campaign"}
              </h3>
              <p className="text-sm text-slate-600">
                Upload only .wav or .mp3 files. The backend serves this asset
                locally for call playback.
              </p>
            </div>
          </div>

          <div className="mt-6 rounded-[1.6rem] border border-dashed border-slate-300 bg-slate-50 p-6">
            <label className="flex flex-col items-center gap-4 text-center text-sm text-slate-600">
              <UploadCloud className="size-8 text-slate-400" />
              <span>Choose a prompt file for this campaign</span>
              <input
                accept=".mp3,.wav,audio/mpeg,audio/wav"
                className="block w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 outline-none"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    uploadMutation.mutate(file);
                  }
                }}
                type="file"
              />
            </label>
          </div>

          <div className="mt-6">
            {audioQuery.isLoading ? (
              <div className="skeleton-block h-48" />
            ) : audioQuery.data?.audio ? (
              <div className="rounded-[1.6rem] border border-slate-200 bg-slate-50 p-5">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="font-medium text-slate-900">
                      {audioQuery.data.audio.original_name}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      {audioQuery.data.audio.mime_type || "audio file"}
                    </p>
                  </div>
                  <Button
                    variant="danger"
                    onPress={() => deleteMutation.mutate()}
                  >
                    <Trash2 className="size-4" />
                    Delete file
                  </Button>
                </div>
                <audio
                  className="mt-5 w-full"
                  controls
                  src={audioQuery.data.audio.file_url}
                />
              </div>
            ) : (
              <div className="rounded-[1.6rem] border border-dashed border-slate-200 px-4 py-10 text-center text-sm text-slate-500">
                No audio file is attached to this campaign yet.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
