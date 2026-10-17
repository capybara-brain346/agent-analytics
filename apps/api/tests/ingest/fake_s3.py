import io

from botocore.exceptions import ClientError


def _error(code: str, op: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, op)


class FakeS3:
    def __init__(self, buckets: tuple[str, ...] = ()) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {b: {} for b in buckets}
        self.uploads: dict[str, dict[int, bytes]] = {}
        self.calls: list[str] = []

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise _error("404", "HeadBucket")

    def create_bucket(self, Bucket):
        self.calls.append("create_bucket")
        self.buckets[Bucket] = {}

    def put_object(self, Bucket, Key, Body):
        self.calls.append("put_object")
        self.buckets[Bucket][Key] = Body

    def create_multipart_upload(self, Bucket, Key):
        self.calls.append("create_multipart_upload")
        upload_id = f"u{len(self.uploads)}"
        self.uploads[upload_id] = {}
        return {"UploadId": upload_id}

    def upload_part(self, Bucket, Key, UploadId, PartNumber, Body):
        self.calls.append("upload_part")
        self.uploads[UploadId][PartNumber] = Body
        return {"ETag": f"e{PartNumber}"}

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):
        self.calls.append("complete_multipart_upload")
        parts = self.uploads.pop(UploadId)
        numbers = [p["PartNumber"] for p in MultipartUpload["Parts"]]
        self.buckets[Bucket][Key] = b"".join(parts[n] for n in numbers)

    def abort_multipart_upload(self, Bucket, Key, UploadId):
        self.calls.append("abort_multipart_upload")
        self.uploads.pop(UploadId, None)

    def get_object(self, Bucket, Key):
        try:
            return {"Body": io.BytesIO(self.buckets[Bucket][Key])}
        except KeyError:
            raise _error("NoSuchKey", "GetObject") from None

    def delete_object(self, Bucket, Key):
        self.buckets[Bucket].pop(Key, None)

    def list_objects_v2(self, Bucket, Prefix="", ContinuationToken=None):
        keys = sorted(k for k in self.buckets[Bucket] if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start : start + 2]
        more = start + 2 < len(keys)
        out = {
            "Contents": [{"Key": k, "Size": len(self.buckets[Bucket][k])} for k in page],
            "IsTruncated": more,
        }
        if more:
            out["NextContinuationToken"] = str(start + 2)
        return out
