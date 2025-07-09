const baseUrl = window.location.origin;

const videoPlayer = document.getElementById("videoPlayer");

const fetchVideos = async () => {
    //const res = await fetch(baseUrl + "/api/videos"); // For frontend-only version
    //const videoList = await res.json();
    const videos = document.getElementById("videos");
    videos.innerHTML = "";
    for (const video of videoList) {
        console.log(video);
        const li = document.createElement("li");
        li.innerHTML = `
                 <p style="text-decoration: underline; cursor: pointer; width: 20%;" id="choose_${video.name}">${video.name}</p>
                 <p style="width: 20%;">${video.video_duration}</p>
                 <p style="width: 20%;">${new Date(video.start_timestamp).toLocaleString("fi-FI", {timeZone: "Europe/Helsinki"})}</p>
                 <a href="${baseUrl + video.video_path}" download style="width: 20%;">Download</a>
                 <button id="delete_${video.name}">Delete</button>`;

        li.style.display = "flex";
        li.style.justifyContent = "space-between";
        li.style.alignItems = "center";
        li.style.padding = "8px";
        li.style.borderBottom = "1px solid #ccc";
        li.style.cursor = "pointer";

        videos.appendChild(li);
        document.getElementById(`choose_${video.name}`).addEventListener("click", async (e) => {
            Plotter(video)
            videoPlayer.src = baseUrl + "/" + video.video_path;
            videoPlayer.style.display = "block";
            videoPlayer.play();
        });

        document.getElementById(`delete_${video.name}`).addEventListener("click", async () => {
            const response = await fetch(`${baseUrl + "/api/" + video.video_path}`, {
                method: "DELETE"
            })
            console.log(`${baseUrl + "/api/" + video.video_path}`, response.statusText);
        });
    }
}
fetchVideos();

const uploadForm = document.getElementById("uploadForm");
uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(uploadForm);
    
    // Convert start_timestamp to ISO string
    formData.set("start_timestamp", new Date(formData.get("start_timestamp")).toISOString());

    const response = await fetch(baseUrl + "/api/videos", {
        method: "POST",
        body: formData
    });
    const data = await response.json();
    console.log(data);
});

/* db is empty for now
const fetchVideo = async () => {
    const response = await fetch(baseUrl + "/api/videos");
    const data = await response.json();
    console.log("fetchVideo:", data);
    videoPlayer.src = data[0].video_path;
}


const fetchVideo = async () => {
    const response = await fetch(baseUrl + "/api/videos/files");
    const data = await response.json();
    console.log(data);
    videoPlayer.src = baseUrl + data[Object.keys(data)[0]].video_path;
    //videoPlayer.play();
}
fetchVideo();
*/