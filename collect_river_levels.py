"""
東京の主要河川 水位データ収集スクリプト（プロトタイプ）
=====================================================

データ源：国土交通省「水文水質データベース」(http://www1.river.go.jp/)

【重要・利用上の注意】
このサイトは「ツール等による自動的なデータ収集等はサーバに負荷がかかり、
情報提供できなくなる恐れがありますので原則としてご遠慮ください」と明記しています。
そのため本スクリプトは:
  - 5分/1分単位のポーリングではなく、1日数回程度のバッチ実行を想定
  - 1回のリクエストで最大31日分をまとめて取得（頻繁な細切れリクエストを避ける）
  - リクエスト間に必ずスリープを挟む
という節度を守った設計にしています。継続的なリアルタイム監視が必要になった場合は、
（一財）河川情報センターの「水防災オープンデータ提供サービス」等、正式な配信契約への
切り替えを検討してください。

【観測局IDについて】
下記 STATIONS には、水文水質データベースの「水系単位の観測所一覧検索」で
確認した実際の観測局IDを設定済みです（多摩川・荒川・江戸川・隅田川）。
別の観測所を追加/変更したい場合は http://www1.river.go.jp/ で河川名を検索し、
観測所情報画面URLの `SiteInfo.exe?ID=...` の数字列を控えて置き換えてください。

【対象外：神田川】
神田川は国管理でなく東京都管理河川のため、このデータベースには収録されていません。
神田川を含めたい場合は「東京都水防災総合情報システム」側の別ルートでの収集が必要です
（飯田橋・和田見橋などの観測所が候補。サイト構造の解析が必要なため別途対応）。

依存パッケージ:
    pip install requests beautifulsoup4 pandas --break-system-packages
"""

import time
import datetime as dt
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
import pandas as pd

BASE_URL = (
    "http://www1.river.go.jp/cgi-bin/DspWaterData.exe"
    "?KIND=1&ID={station_id}&BGNDATE={bgn}&ENDDATE={end}&KAWABOU=NO"
)

# 1回のリクエストで取得できるのは最大31日分
MAX_DAYS_PER_REQUEST = 31
# リクエスト間隔（秒）。サーバー負荷配慮のため、必ず数秒以上あける。
REQUEST_INTERVAL_SEC = 5

# 通常のブラウザに近いヘッダーでアクセスする（既定のPython UAは弾かれることがある）
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "http://www1.river.go.jp/",
}

_session = requests.Session()
_session.headers.update(_HEADERS)
_session_primed = False


def _get_session() -> requests.Session:
    """トップページに一度アクセスしてからCookieを保持したセッションを使い回す。"""
    global _session_primed
    if not _session_primed:
        try:
            _session.get("http://www1.river.go.jp/", timeout=20)
        except requests.RequestException:
            pass  # プライミングに失敗しても本リクエストは試す
        _session_primed = True
    return _session


@dataclass
class Station:
    river: str          # 河川名（表示用）
    name: str            # 観測所名（表示用）
    station_id: str       # 観測局ID（要確認・要置換）


# ── 監視対象：ここに実際の観測局IDを埋めてください ──────────────
STATIONS = [
    Station(river="多摩川", name="田園調布（下）", station_id="303051283310020"),  # 確認済み
    Station(river="荒川",   name="南砂町",             station_id="303041283309120"),  # 確認済み
    Station(river="江戸川", name="高砂",             station_id="303031283305480"),  # 確認済み
    Station(river="隅田川", name="隅田水門（裏）",     station_id="303041283309091"),  # 確認済み
    # 神田川は東京都管理河川のため、国交省「水文水質データベース」には収録されていません。
    # データが必要な場合は「東京都水防災総合情報システム」（飯田橋・和田見橋 等の観測所）
    # から別途収集する必要があります（本スクリプトの対象外）。
]


def fetch_water_level(station: Station, bgn_date: dt.date, end_date: dt.date) -> pd.DataFrame:
    """指定観測局・期間の水位データを取得して DataFrame で返す。

    水文水質データベースは 01:00〜24:00 表記のため、24:00 は翌日 00:00 に補正する。
    """
    if (end_date - bgn_date).days > MAX_DAYS_PER_REQUEST:
        raise ValueError(f"一度に取得できるのは最大{MAX_DAYS_PER_REQUEST}日分です")

    url = BASE_URL.format(
        station_id=station.station_id,
        bgn=bgn_date.strftime("%Y%m%d"),
        end=end_date.strftime("%Y%m%d"),
    )

    session = _get_session()

    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")

    # ページ本体に iframe でデータ表が埋め込まれている構成のことがある。
    # iframe の src が別URLの場合はそちらを取得し直す。
    iframe = soup.find("iframe")
    if iframe and iframe.get("src"):
        iframe_url = requests.compat.urljoin(url, iframe["src"])
        resp2 = session.get(iframe_url, timeout=20)
        resp2.raise_for_status()
        resp2.encoding = resp2.apparent_encoding
        soup = BeautifulSoup(resp2.text, "html.parser")

    tables = soup.find_all("table")
    if not tables:
        raise RuntimeError(
            f"データ表が見つかりませんでした（{station.river} / {station.name}）。"
            " サイト構造が変わったか、観測局IDが誤っている可能性があります。"
        )

    rows = []
    for tr in tables[0].find_all("tr"):
        cells = [td.get_text().strip().replace("\u3000", "") for td in tr.find_all("td")]
        if len(cells) == 3:
            rows.append(cells)

    if not rows:
        return pd.DataFrame(columns=["timestamp", "water_level_m", "river", "station"])

    df = pd.DataFrame(rows, columns=["date", "time", "water_level_m"])
    df["timestamp"] = (df["date"] + " " + df["time"]).apply(_parse_datetime)
    df["water_level_m"] = pd.to_numeric(df["water_level_m"], errors="coerce")
    df["river"] = station.river
    df["station"] = station.name
    df = df.dropna(subset=["timestamp", "water_level_m"])
    return df[["timestamp", "river", "station", "water_level_m"]].sort_values("timestamp")


def _parse_datetime(text: str) -> "pd.Timestamp | None":
    """'YYYY/MM/DD HH:MM' 形式（24:00は翌日00:00に補正）を Timestamp に変換。"""
    text = text.strip()
    try:
        if text.endswith("24:00"):
            date_part = text[:-5].strip()
            ts = pd.to_datetime(date_part + " 00:00", format="%Y/%m/%d %H:%M")
            return ts + pd.Timedelta(days=1)
        return pd.to_datetime(text, format="%Y/%m/%d %H:%M")
    except ValueError:
        return None


def collect_all(bgn_date: dt.date, end_date: dt.date, out_csv: str = "river_levels.csv") -> pd.DataFrame:
    """STATIONS 全件を収集し、CSVに追記保存する（重複は timestamp+station で除去）。"""
    frames = []
    for i, station in enumerate(STATIONS):
        if station.station_id.startswith("PLACEHOLDER"):
            print(f"[SKIP] {station.river} / {station.name} … 観測局IDが未設定です")
            continue
        print(f"[FETCH] {station.river} / {station.name} ({bgn_date}〜{end_date})")
        try:
            df = fetch_water_level(station, bgn_date, end_date)
            frames.append(df)
        except requests.exceptions.HTTPError as e:
            hint = ""
            if e.response is not None and e.response.status_code == 403:
                hint = "（Bot判定でブロックされた可能性。ヘッダー/セッション設定を見直すか、時間を置いて再実行してください）"
            print(f"[ERROR] {station.river} / {station.name}: {e} {hint}")
        except Exception as e:
            print(f"[ERROR] {station.river} / {station.name}: {e}")
        if i < len(STATIONS) - 1:
            time.sleep(REQUEST_INTERVAL_SEC)

    if not frames:
        print("取得できたデータがありませんでした。観測局IDを確認してください。")
        return pd.DataFrame()

    new_df = pd.concat(frames, ignore_index=True)

    try:
        existing = pd.read_csv(out_csv, parse_dates=["timestamp"])
        combined = pd.concat([existing, new_df], ignore_index=True)
    except FileNotFoundError:
        combined = new_df

    combined = combined.drop_duplicates(subset=["timestamp", "station"]).sort_values(
        ["river", "station", "timestamp"]
    )
    combined.to_csv(out_csv, index=False)
    print(f"→ {out_csv} に保存しました（累計 {len(combined)} 行）")
    return combined


if __name__ == "__main__":
    # 例：直近3日分を取得（cron等で1日1〜2回実行する想定）
    today = dt.date.today()
    collect_all(bgn_date=today - dt.timedelta(days=3), end_date=today)
