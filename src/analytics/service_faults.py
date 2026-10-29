"""Safe typed failures; provider bodies and credentials never enter UI metadata."""
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
import math
import httpx


class ModelServiceError(httpx.RequestError):
    def __init__(self,code,message,*,retry_after=None,retryable=True):
        super().__init__(message)
        self.code=code;self.retry_after=retry_after;self.retryable=retryable

    def result(self):
        result={'status':'error','error_code':self.code,'error_message':str(self),'retryable':self.retryable}
        if self.retry_after is not None:
            result['retry_after_seconds']=self.retry_after
            result['retry_at']=(datetime.now(timezone.utc)+timedelta(seconds=self.retry_after)).isoformat()
        return result


def retry_seconds(value,now=None):
    """Accept seconds or an HTTP date; never derive a deadline from error text."""
    if not value or len(str(value))>100:return None
    try:
        seconds=float(value)
    except (TypeError,ValueError):
        try:
            instant=parsedate_to_datetime(value)
            if instant.tzinfo is None:return None
            seconds=(instant-(now or datetime.now(timezone.utc))).total_seconds()
        except (TypeError,ValueError,OverflowError):return None
    return math.ceil(seconds) if math.isfinite(seconds) and 0<=seconds<=604800 else None
