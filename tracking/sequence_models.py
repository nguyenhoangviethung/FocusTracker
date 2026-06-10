from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class TemporalAttention(nn.Module):
    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        attention_hidden = max(1, hidden_size // 2)
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, attention_hidden),
            nn.Tanh(),
            nn.Linear(attention_hidden, 1),
        )

    def forward(self, rnn_output: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        attn_weights = self.attention(rnn_output)
        attn_weights = F.softmax(attn_weights, dim=1)
        context = torch.sum(attn_weights * rnn_output, dim=1)
        return context, attn_weights


class EngagementGRU(nn.Module):
    """Bidirectional GRU + attention architecture from engagement-cpu."""

    def __init__(
        self,
        input_size: int = 90,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.3,
        **_: object,
    ) -> None:
        super().__init__()
        self.feature_extractor = nn.Sequential(
            nn.LayerNorm(input_size),
            nn.Linear(input_size, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.gru = nn.GRU(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.attention = TemporalAttention(hidden_size * 2)
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.LayerNorm(hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        x = self.feature_extractor(inputs)
        gru_out, _ = self.gru(x)
        context, _ = self.attention(gru_out)
        logits = self.classifier(context)
        return logits.view(-1)


class BasicGRUClassifier(nn.Module):
    def __init__(
        self,
        input_size: int = 90,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.3,
        **_: object,
    ) -> None:
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=False,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, 1)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        output, _ = self.gru(inputs)
        last_hidden = output[:, -1, :]
        logits = self.classifier(self.dropout(last_hidden))
        return logits.view(-1)


class TemporalConvBlock(nn.Module):
    def __init__(self, channels: int, kernel_size: int, dilation: int, dropout: float) -> None:
        super().__init__()
        padding = (kernel_size - 1) * dilation // 2
        self.conv1 = nn.Conv1d(channels, channels, kernel_size=kernel_size, dilation=dilation, padding=padding)
        self.bn1 = nn.BatchNorm1d(channels)
        self.conv2 = nn.Conv1d(channels, channels, kernel_size=kernel_size, dilation=dilation, padding=padding)
        self.bn2 = nn.BatchNorm1d(channels)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = x
        x = self.conv1(x)
        x = self.bn1(x)
        x = F.relu(x, inplace=True)
        x = self.dropout(x)
        x = self.conv2(x)
        x = self.bn2(x)
        x = self.dropout(x)
        return F.relu(x + residual, inplace=True)


class EngagementTCN(nn.Module):
    """Temporal convolution architecture from engagement-cpu."""

    def __init__(
        self,
        input_size: int = 90,
        hidden_size: int = 64,
        dropout: float = 0.3,
        kernel_size: int = 3,
        num_blocks: int = 3,
        tcn_blocks: int | None = None,
        **_: object,
    ) -> None:
        super().__init__()
        if tcn_blocks is not None:
            num_blocks = int(tcn_blocks)
        self.input_proj = nn.Sequential(
            nn.LayerNorm(input_size),
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
        )
        dilations = [2**index for index in range(num_blocks)]
        blocks = [
            TemporalConvBlock(hidden_size, kernel_size=kernel_size, dilation=dilation, dropout=dropout)
            for dilation in dilations
        ]
        self.tcn = nn.Sequential(*blocks)
        self.head = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        x = self.input_proj(inputs)
        x = x.transpose(1, 2)
        x = self.tcn(x)
        pooled_avg = torch.mean(x, dim=-1)
        pooled_max = torch.amax(x, dim=-1)
        pooled = torch.cat([pooled_avg, pooled_max], dim=-1)
        logits = self.head(pooled)
        return logits.view(-1)


def build_sequence_model(
    model_name: str,
    input_size: int = 90,
    hidden_size: int = 64,
    num_layers: int = 2,
    dropout: float = 0.3,
    kernel_size: int = 3,
    tcn_blocks: int = 3,
    tcn_kernel_size: int | None = None,
    **kwargs: object,
) -> nn.Module:
    name = model_name.strip().lower()
    if tcn_kernel_size is not None:
        kernel_size = int(tcn_kernel_size)

    if name == "gru":
        return EngagementGRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            **kwargs,
        )
    if name in {"gru_basic", "simple_gru"}:
        return BasicGRUClassifier(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=max(1, num_layers),
            dropout=dropout,
            **kwargs,
        )
    if name in {"tcn", "1dcnn", "temporal_cnn"}:
        return EngagementTCN(
            input_size=input_size,
            hidden_size=hidden_size,
            dropout=dropout,
            kernel_size=kernel_size,
            num_blocks=tcn_blocks,
            **kwargs,
        )

    raise ValueError(f"Unsupported deploy model_name: {model_name}")


class ProbabilityWrapper(nn.Module):
    """Export wrapper: ONNX receives already-normalized sequence and returns probability."""

    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, sequence: torch.Tensor) -> torch.Tensor:
        logits = self.model(sequence)
        return torch.sigmoid(logits)
