 // Tag logic

 class Tag {
    constructor(mac, temperature, humidity, pressure, acceleration_x, acceleration_y, acceleration_z, created_at) {
        this.mac = mac;
        this.temperature = temperature;
        this.humidity = humidity;
        this.pressure = pressure;
        this.acceleration_x = acceleration_x;
        this.acceleration_y = acceleration_y;
        this.acceleration_z = acceleration_z;
        this.created_at = created_at;
    }
}


const fetchTags = async (video) => {
    // Fetch tags from 1 hour before and 1 hour after the video start time
    const start_t = new Date(video.start_timestamp);
    //const start = new Date(start_t.getTime() - (60 * 1000 * 5));
    const start = dateFns.sub(start_t, {minutes: 5});

    //const end_t = new Date(start.getTime() + video.video_duration * 1000);
    const end = dateFns.add(new Date(start.getTime() + video.video_duration * 1000), {
        minutes: 10
    });

    console.log("start:", start, "end:", end);
    
    let tags = {};
    const tagsURL = window.location.origin + "/api/tags/range/" + start.toISOString() + "/" + end.toISOString();
    console.log("tagsURL:", tagsURL);

    const tagResponse = await fetch(tagsURL);
    
    const tagsData = await tagResponse.json();
    
    for (const tag of tagsData[0]) {
        const tagObject = new Tag(tag.mac, tag.temperature, tag.humidity, tag.pressure, tag.acceleration_x, tag.acceleration_y, tag.acceleration_z, tag.created_at);
        if (!tags[tagObject.mac]) {
            tags[tagObject.mac] = [];
        }
        tags[tagObject.mac].push(tagObject);
    }
    console.log(tags);
    return tags;
}

const csvForm = document.getElementById("csvForm");
const csvDownloadButton = document.getElementById("csvDownloadButton");
csvForm.addEventListener("change", (e) => {
    e.preventDefault();
    const csvFormData = new FormData(csvForm);
    const start = csvFormData.get("start");
    const end = csvFormData.get("end");

    const startDate = new Date(start);
    const endDate = new Date(end);
    if (startDate >= endDate) {
        alert("Start date must be before end date.");
        return;
    }
    
    const csvURL = window.location.origin + "/api/tags/csv?start=" + startDate.toISOString() + "&end=" + endDate.toISOString();
    console.log("csvURL:", csvURL);
    
    csvDownloadButton.href = csvURL
    csvDownloadButton.download = `tags_${start}_${end}.csv`; // Set the download filename
    //csvDownloadButton.click();
});



// Plot logic
var layout = {
    autosize: true,
    width: 1000,
    height: 500,
    xaxis: {
        autorange: true,
        rangeslider: {autorange: true, bgcolor: "#222"},
        color: "#e0e0e0",
        gridcolor: "#333",
        zerolinecolor: "#444",
        automargin: true
    },
    yaxis: {
        color: "#ffffff",
        gridcolor: "#333",
        zerolinecolor: "#444",
        automargin: true
    },
    paper_bgcolor: "#212121",
    plot_bgcolor: "#212121",
    font: { color: "#e0e0e0" },
    legend: { font: { color: "#e0e0e0" }, bgcolor: "#111" }
}

const plotTags = (tags) => {
    const data = [
        {
            x: tags[Object.keys(tags)[0]].map(tag => new Date(tag.created_at)),
            y: tags[Object.keys(tags)[0]].map(tag => tag.acceleration_x),
            type: "scatter",
            mode: "lines+markers",
            name: Object.keys(tags)[0] + " x"
        },
        {
            x: tags[Object.keys(tags)[0]].map(tag => new Date(tag.created_at)),
            y: tags[Object.keys(tags)[0]].map(tag => tag.acceleration_y),
            type: "scatter",
            mode: "lines+markers",
            name: Object.keys(tags)[0] + " y"
        },
        {
            x: tags[Object.keys(tags)[0]].map(tag => new Date(tag.created_at)),
            y: tags[Object.keys(tags)[0]].map(tag => tag.acceleration_z),
            type: "scatter",
            mode: "lines+markers",
            name: Object.keys(tags)[0] + " z"
        }
    ]
    console.log(data)

    const config = {
        responsive: true
    }
    Plotly.newPlot("acc-plot", data, {...layout, template: "plotly_dark"}, config);
}


function Plotter(video) {
    // .then ensures the tags are fetched before plotting
    fetchTags(video).then(tags => {
        plotTags(tags);
         // First tag's timestamp

        videoPlayer.addEventListener("timeupdate", async function() {
            try {
                const videoStartTime = new Date(video.start_timestamp);

                let videoOffset = videoPlayer.currentTime; // seconds
                console.log("videoOffset:", videoOffset);


                let windowStart = new Date(videoStartTime.getTime() + (videoOffset) * 1000 - 10000); // 10 seconds before tag
                console.log("windowStart:", windowStart);
                let windowEnd = new Date(videoStartTime.getTime() + (videoOffset) * 1000); // 10 seconds

                await Plotly.relayout("acc-plot", {
                    "xaxis.range": [windowStart, windowEnd]
                });
                
            } catch (err) {
                console.error("Error updating plot:", err);
            }
        });
    });
}

