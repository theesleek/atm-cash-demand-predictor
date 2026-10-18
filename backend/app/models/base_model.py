from __future__ import annotations

from abc import ABC, abstractmethod


class BaseModel(ABC):
    @abstractmethod
    def fit(self, X, y):
        raise NotImplementedError

    @abstractmethod
    def predict(self, X):
        raise NotImplementedError
